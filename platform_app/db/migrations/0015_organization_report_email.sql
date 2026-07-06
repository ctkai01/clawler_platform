-- Per-organization config for the daily report email (recipient + CC list).
-- One row per org, created on first save from the Settings page.
CREATE TABLE organization_report_email (
    organization_id BIGINT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    recipient_email TEXT NOT NULL,
    cc_emails TEXT[] NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
