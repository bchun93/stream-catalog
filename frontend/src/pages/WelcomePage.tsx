import { Link } from "react-router-dom";
import { Clapperboard, Film, HardDrive, ScanSearch, Upload } from "lucide-react";
import { PageHeader } from "../components/ui/PageHeader";

export function WelcomePage() {
  return (
    <>
      <PageHeader
        title="Welcome to Relay"
        description="A prototype for validating media supply chain features — from metadata and assets to QC and delivery."
      />

      <section className="welcome-intro card card-padded">
        <p>
          Relay is a prototype that I have been building to validate media supply chain features.
          The idea for Relay was inspired by the content operations problems I was solving. Among
          the problems I was solving were manual metadata entry, media asset management, and
          automated workflows for QC and delivery. The vision for Relay is to become a fully
          AI-native media supply chain tool.
        </p>
        <p>
          Start with the two workflows below — they are the most complete today. Use the sidebar
          anytime to jump into <strong>Titles</strong>, <strong>Media assets</strong>,{" "}
          <strong>Upload</strong>, or <strong>Delivery</strong>.
        </p>
      </section>

      <div className="welcome-guides">
        <article className="welcome-guide card card-padded">
          <header className="welcome-guide-header">
            <span className="welcome-guide-icon" aria-hidden>
              <Film size={22} />
            </span>
            <div>
              <h2>Titles — metadata & artwork from TMDB</h2>
              <p className="welcome-guide-lede">
                Create a movie or series, import core metadata from TMDB, then fetch and save
                posters, backdrops, logos, and stills.
              </p>
            </div>
          </header>

          <ol className="welcome-steps">
            <li>
              <strong>Open Titles</strong>
              <span>
                Go to <Link to="/titles">Titles</Link> and click <em>New title</em>.
              </span>
            </li>
            <li>
              <strong>Search TMDB</strong>
              <span>
                In the create sheet, use <em>Search by title name…</em> under metadata lookup.
                Pick a movie or TV result to import name, synopsis, genres, cast, runtime, and
                related fields.
              </span>
            </li>
            <li>
              <strong>Import a series hierarchy (optional)</strong>
              <span>
                For TV results, preview the hierarchy, then apply it to create the series,
                seasons, and episodes in one pass.
              </span>
            </li>
            <li>
              <strong>Save the title</strong>
              <span>
                Review the Details tab, adjust any fields, then <em>Save title</em>. Artwork
                needs a saved title id.
              </span>
            </li>
            <li>
              <strong>Fetch artwork</strong>
              <span>
                Open the <em>Artwork</em> tab on that title. Fetch images from TMDB, choose
                posters / backdrops / logos / stills, assign roles, and save them onto the
                title.
              </span>
            </li>
          </ol>

          <div className="welcome-guide-actions">
            <Link to="/titles" className="btn btn-primary">
              <span className="btn-icon" aria-hidden>
                <Film size={16} />
              </span>
              Go to Titles
            </Link>
          </div>
        </article>

        <article className="welcome-guide card card-padded">
          <header className="welcome-guide-header">
            <span className="welcome-guide-icon" aria-hidden>
              <ScanSearch size={22} />
            </span>
            <div>
              <h2>Video QC — Amazon Rekognition</h2>
              <p className="welcome-guide-lede">
                Analyze H.264 MP4/MOV masters for segments, moderation labels, and on-screen
                objects. Results appear as a time-coded QC layer on the asset.
              </p>
            </div>
          </header>

          <ol className="welcome-steps">
            <li>
              <strong>Register a video asset</strong>
              <span>
                Upload a file via <Link to="/upload">Upload</Link> (S3 ingest bucket), then
                register it under <Link to="/assets">Media assets</Link> — or open an existing
                video asset that already has an <code>s3://</code> storage URI.
              </span>
            </li>
            <li>
              <strong>Open the asset → QC tab</strong>
              <span>
                From Media assets, open the asset detail page and select the <em>QC</em> tab.
              </span>
            </li>
            <li>
              <strong>Confirm the video source</strong>
              <span>
                QC reads from the asset&apos;s S3 URI. Use <em>Choose video</em> only if you need
                to point at a different key in the ingest bucket.
              </span>
            </li>
            <li>
              <strong>Run Analyze</strong>
              <span>
                Click <em>Analyze</em> to start Segments (technical cues &amp; shots), Moderation
                (compliance flags), and Labels (objects &amp; scenes). Jobs run asynchronously in
                AWS.
              </span>
            </li>
            <li>
              <strong>Refresh results</strong>
              <span>
                Use <em>Refresh</em> while jobs are in progress. When status is SUCCEEDED,
                review the cue timeline, moderation hits, and searchable labels. Drain the
                notification queue if results seem stuck after jobs succeed.
              </span>
            </li>
          </ol>

          <p className="welcome-note">
            Supported for QC today: H.264 in <strong>MP4</strong> or <strong>MOV</strong>, stored
            in the configured ingest S3 bucket. Local/dev also needs the Rekognition stack
            (SNS/SQS/DynamoDB) and AWS credentials described in the project docs.
          </p>

          <div className="welcome-guide-actions">
            <Link to="/assets" className="btn btn-primary">
              <span className="btn-icon" aria-hidden>
                <HardDrive size={16} />
              </span>
              Go to Media assets
            </Link>
            <Link to="/upload" className="btn btn-subtle">
              <span className="btn-icon" aria-hidden>
                <Upload size={16} />
              </span>
              Upload video
            </Link>
          </div>
        </article>
      </div>

      <section className="welcome-also card card-padded">
        <header className="welcome-also-header">
          <Clapperboard size={18} aria-hidden />
          <h2>Also in Relay</h2>
        </header>
        <ul className="welcome-also-list">
          <li>
            <Link to="/upload">Upload</Link> — drop files into the ingest S3 bucket with unique
            keys, then link them to titles as media assets.
          </li>
          <li>
            <Link to="/delivery">Delivery</Link> — create packages against platform delivery
            profiles (e.g. Amazon Prime Video SVOD) and validate title assets against the
            profile rules.
          </li>
        </ul>
      </section>
    </>
  );
}
