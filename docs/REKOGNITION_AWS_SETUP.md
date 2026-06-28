# Amazon Rekognition Video — AWS setup (run these yourself)

This is the infrastructure bundle for the Rekognition Video integration. **Relay never
creates or mutates AWS resources at runtime** — you run the commands below once, then put the
resulting ARNs/URLs into the app's environment (Render + GitHub Actions + your local `.env`).

Everything is **least-privilege** and region-pinned. Run top-to-bottom.

> Architecture recap: `Relay → StartX` (reads the H.264 MP4 proxy from S3, in place) →
> Rekognition runs async → publishes completion to **SNS** → fans out to **SQS (+DLQ)** →
> a scheduled consumer drains SQS, calls `GetX` (paginated), and writes detections to
> **DynamoDB**. We never poll `GetX` for *status* — status comes only from SQS.

---

## 0. Shared variables

```bash
# ---- edit these ----
export AWS_REGION=us-east-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Decision (1A): we analyze the proxy IN PLACE from the asset's existing storage bucket.
# Set this to the bucket your Relay assets already live in (INGEST_S3_BUCKET), OR a
# dedicated analysis bucket if you prefer to copy proxies there first.
export S3_ANALYSIS_BUCKET=relay-rekognition-analysis

# Names (the SNS topic name MUST start with "AmazonRekognition")
export SNS_TOPIC_NAME=AmazonRekognition-relay-completion
export SQS_QUEUE_NAME=relay-rekognition-completion
export SQS_DLQ_NAME=relay-rekognition-completion-dlq
export DDB_JOBS_TABLE=relay_rekognition_jobs
export DDB_DETECTIONS_TABLE=relay_rekognition_detections
export REKO_SERVICE_ROLE_NAME=RelayRekognitionServiceRole
export APP_IAM_USER_NAME=relay-rekognition-app
```

---

## 1. S3 analysis bucket (decision 1A: analyze in place)

If you will use an existing bucket (your current `INGEST_S3_BUCKET`), **skip the create step**
and just confirm Block Public Access is on. To create a dedicated bucket:

```bash
# Create (us-east-1 must NOT pass LocationConstraint; all other regions must)
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$S3_ANALYSIS_BUCKET" --region "$AWS_REGION"
else
  aws s3api create-bucket --bucket "$S3_ANALYSIS_BUCKET" --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"
fi

# Block ALL public access
aws s3api put-public-access-block --bucket "$S3_ANALYSIS_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

> Rekognition reads whatever bucket the **service role** (section 5) is granted `s3:GetObject`
> on, in the **same region** as the Rekognition call. Make sure your proxies and this setup
> share one region.

---

## 2. SNS completion topic

```bash
export SNS_TOPIC_ARN=$(aws sns create-topic \
  --name "$SNS_TOPIC_NAME" --region "$AWS_REGION" \
  --query TopicArn --output text)
echo "SNS_TOPIC_ARN=$SNS_TOPIC_ARN"
```

The name **must** start with `AmazonRekognition` so the AWS-managed
`AmazonRekognitionServiceRole` (if you use it) is allowed to publish to it.

---

## 3. SQS main queue + dead-letter queue + SNS→SQS subscription

```bash
# 3a. Dead-letter queue first (so we can reference its ARN)
export SQS_DLQ_URL=$(aws sqs create-queue \
  --queue-name "$SQS_DLQ_NAME" --region "$AWS_REGION" \
  --attributes MessageRetentionPeriod=1209600 \
  --query QueueUrl --output text)

export SQS_DLQ_ARN=$(aws sqs get-queue-attributes \
  --queue-url "$SQS_DLQ_URL" --attribute-names QueueArn --region "$AWS_REGION" \
  --query 'Attributes.QueueArn' --output text)

# 3b. Main queue with a redrive policy → DLQ after 5 failed receives,
#     long-poll friendly (ReceiveMessageWaitTimeSeconds=10), 5 min visibility.
export SQS_QUEUE_URL=$(aws sqs create-queue \
  --queue-name "$SQS_QUEUE_NAME" --region "$AWS_REGION" \
  --attributes "{
    \"ReceiveMessageWaitTimeSeconds\":\"10\",
    \"VisibilityTimeout\":\"300\",
    \"MessageRetentionPeriod\":\"345600\",
    \"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$SQS_DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"5\\\"}\"
  }" \
  --query QueueUrl --output text)

export SQS_QUEUE_ARN=$(aws sqs get-queue-attributes \
  --queue-url "$SQS_QUEUE_URL" --attribute-names QueueArn --region "$AWS_REGION" \
  --query 'Attributes.QueueArn' --output text)
echo "SQS_QUEUE_URL=$SQS_QUEUE_URL"
echo "SQS_QUEUE_ARN=$SQS_QUEUE_ARN"
```

### 3c. Allow SNS to send to the SQS queue (resource policy on the queue)

```bash
cat > /tmp/sqs-access-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSNSPublish",
      "Effect": "Allow",
      "Principal": { "Service": "sns.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "$SQS_QUEUE_ARN",
      "Condition": { "ArnEquals": { "aws:SourceArn": "$SNS_TOPIC_ARN" } }
    }
  ]
}
EOF

aws sqs set-queue-attributes --queue-url "$SQS_QUEUE_URL" --region "$AWS_REGION" \
  --attributes Policy="$(cat /tmp/sqs-access-policy.json | tr -d '\n')"
```

### 3d. Subscribe the queue to the topic

**Raw message delivery: DISABLED (`RawMessageDelivery=false`, the default).** We intentionally
keep the **SNS envelope** so the consumer parses the outer notification and then the inner
`Message` (the Rekognition completion JSON). The consumer in Phase 4 is written for this shape.

```bash
aws sns subscribe \
  --topic-arn "$SNS_TOPIC_ARN" \
  --protocol sqs \
  --notification-endpoint "$SQS_QUEUE_ARN" \
  --attributes RawMessageDelivery=false \
  --region "$AWS_REGION"
```

---

## 4. DynamoDB tables (on-demand / PAY_PER_REQUEST)

Schema rationale is documented in Phase 2 of the build. `rekognition_jobs` keys on
`(asset_id, feature)` for natural idempotency, with a GSI on `aws_job_id` for the consumer's
lookup-by-JobId. `rekognition_detections` keys on `asset_id` + a zero-padded composite sort
key so lexicographic order == chronological order.

```bash
# 4a. Jobs table: PK=asset_id, SK=feature, GSI gsi_job_id on aws_job_id
aws dynamodb create-table \
  --table-name "$DDB_JOBS_TABLE" --region "$AWS_REGION" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=asset_id,AttributeType=S \
    AttributeName=feature,AttributeType=S \
    AttributeName=aws_job_id,AttributeType=S \
  --key-schema \
    AttributeName=asset_id,KeyType=HASH \
    AttributeName=feature,KeyType=RANGE \
  --global-secondary-indexes '[
    {
      "IndexName": "gsi_job_id",
      "KeySchema": [{"AttributeName":"aws_job_id","KeyType":"HASH"}],
      "Projection": {"ProjectionType":"INCLUDE","NonKeyAttributes":["asset_id","feature","status"]}
    }
  ]'

# 4b. Detections table: PK=asset_id, SK=sk (composite, zero-padded time)
aws dynamodb create-table \
  --table-name "$DDB_DETECTIONS_TABLE" --region "$AWS_REGION" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=asset_id,AttributeType=S \
    AttributeName=sk,AttributeType=S \
  --key-schema \
    AttributeName=asset_id,KeyType=HASH \
    AttributeName=sk,KeyType=RANGE

# Wait until ACTIVE
aws dynamodb wait table-exists --table-name "$DDB_JOBS_TABLE" --region "$AWS_REGION"
aws dynamodb wait table-exists --table-name "$DDB_DETECTIONS_TABLE" --region "$AWS_REGION"
```

---

## 5. IAM identity #1 — Rekognition service role (`RoleArn` in NotificationChannel)

Rekognition assumes this role to publish completion to SNS and to read the S3 proxy.

```bash
cat > /tmp/reko-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "rekognition.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name "$REKO_SERVICE_ROLE_NAME" \
  --assume-role-policy-document file:///tmp/reko-trust.json

cat > /tmp/reko-perms.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishCompletionToSNS",
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "$SNS_TOPIC_ARN"
    },
    {
      "Sid": "ReadProxyFromS3",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$S3_ANALYSIS_BUCKET/*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name "$REKO_SERVICE_ROLE_NAME" \
  --policy-name RelayRekognitionServiceInline \
  --policy-document file:///tmp/reko-perms.json

export REKOGNITION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${REKO_SERVICE_ROLE_NAME}"
echo "REKOGNITION_ROLE_ARN=$REKOGNITION_ROLE_ARN"
```

> **Managed alternative:** AWS provides `arn:aws:iam::aws:policy/service-role/AmazonRekognitionServiceRole`.
> Attached to a role trusting `rekognition.amazonaws.com`, it grants `sns:Publish` to topics
> named `AmazonRekognition*` and `s3:GetObject`/`s3:GetBucketLocation` on any bucket. The
> inline policy above is **tighter** (one topic, one bucket), which is why we prefer it. If you
> use the managed policy instead, you still get the exact two capabilities Rekognition needs.

---

## 6. IAM identity #2 — Relay app credentials (used by the backend)

Least-privilege for the three `Start*` + three `Get*` ops, SQS consume, S3 read of the proxy,
and the DynamoDB access patterns (incl. the GSI index ARN).

> **Important — don't break existing S3:** Relay's current ingest/storage features already use
> AWS credentials (via `AWS_PROFILE` or `AWS_ACCESS_KEY_ID`). Either (a) attach this policy to
> the **same** identity those features use, or (b) create the new user below **and** also grant
> it the S3 permissions your ingest flow needs. Otherwise ingest/storage will lose access.

```bash
aws iam create-user --user-name "$APP_IAM_USER_NAME"

cat > /tmp/relay-app-perms.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RekognitionStartGet",
      "Effect": "Allow",
      "Action": [
        "rekognition:StartSegmentDetection",
        "rekognition:StartContentModeration",
        "rekognition:StartLabelDetection",
        "rekognition:GetSegmentDetection",
        "rekognition:GetContentModeration",
        "rekognition:GetLabelDetection"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassServiceRoleToRekognition",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "$REKOGNITION_ROLE_ARN",
      "Condition": { "StringEquals": { "iam:PassedToService": "rekognition.amazonaws.com" } }
    },
    {
      "Sid": "ConsumeSQS",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "$SQS_QUEUE_ARN"
    },
    {
      "Sid": "ReadProxyS3",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$S3_ANALYSIS_BUCKET/*"
    },
    {
      "Sid": "DetectionsAndJobsDDB",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DDB_JOBS_TABLE}",
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DDB_JOBS_TABLE}/index/*",
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DDB_DETECTIONS_TABLE}",
        "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${DDB_DETECTIONS_TABLE}/index/*"
      ]
    }
  ]
}
EOF

aws iam put-user-policy \
  --user-name "$APP_IAM_USER_NAME" \
  --policy-name RelayRekognitionAppInline \
  --policy-document file:///tmp/relay-app-perms.json

# Create access keys (store securely — shown once)
aws iam create-access-key --user-name "$APP_IAM_USER_NAME"
```

> `iam:PassRole` is required: when Relay calls `StartX` with
> `NotificationChannel.RoleArn = REKOGNITION_ROLE_ARN`, AWS checks the caller may pass that
> role to Rekognition. Without it, `Start*` fails with AccessDenied.

---

## 7. Environment variables to set

Add these to **Render** (API service), your local **`backend/.env`**, and — for the cron
secret only — **GitHub Actions secrets**. (`*.env.example` files are updated in the repo.)

| Key | Value source |
|-----|--------------|
| `AWS_REGION` | your region (e.g. `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | from section 6 `create-access-key` |
| `AWS_SECRET_ACCESS_KEY` | from section 6 `create-access-key` |
| `S3_ANALYSIS_BUCKET` | `$S3_ANALYSIS_BUCKET` |
| `REKOGNITION_ROLE_ARN` | `$REKOGNITION_ROLE_ARN` |
| `REKOGNITION_SNS_TOPIC_ARN` | `$SNS_TOPIC_ARN` |
| `REKOGNITION_SQS_QUEUE_URL` | `$SQS_QUEUE_URL` |
| `DDB_JOBS_TABLE` | `$DDB_JOBS_TABLE` |
| `DDB_DETECTIONS_TABLE` | `$DDB_DETECTIONS_TABLE` |
| `REKOGNITION_CONSUMER_SECRET` | a long random string (e.g. `openssl rand -hex 32`) |

> Local dev uses your existing `AWS_PROFILE` if set (same as the S3 ingest flow). The
> `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` form is for Render/CI where SSO isn't available.

---

## 8. DLQ redrive (operations)

Poison messages (failures the consumer can't process) move to the DLQ after 5 receives.
To inspect and redrive after fixing the cause:

```bash
# Peek how many are stuck
aws sqs get-queue-attributes --queue-url "$SQS_DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages --region "$AWS_REGION"

# Start a redrive from DLQ back to the main queue
aws sqs start-message-move-task \
  --source-arn "$SQS_DLQ_ARN" \
  --destination-arn "$SQS_QUEUE_ARN" \
  --region "$AWS_REGION"
```

---

## 9. Teardown (if you ever need it)

```bash
aws dynamodb delete-table --table-name "$DDB_JOBS_TABLE" --region "$AWS_REGION"
aws dynamodb delete-table --table-name "$DDB_DETECTIONS_TABLE" --region "$AWS_REGION"
aws sns delete-topic --topic-arn "$SNS_TOPIC_ARN" --region "$AWS_REGION"
aws sqs delete-queue --queue-url "$SQS_QUEUE_URL" --region "$AWS_REGION"
aws sqs delete-queue --queue-url "$SQS_DLQ_URL" --region "$AWS_REGION"
aws iam delete-user-policy --user-name "$APP_IAM_USER_NAME" --policy-name RelayRekognitionAppInline
aws iam delete-role-policy --role-name "$REKO_SERVICE_ROLE_NAME" --policy-name RelayRekognitionServiceInline
# (delete access keys, then) aws iam delete-user / delete-role
```
