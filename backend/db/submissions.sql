-- Projects uploaded through POST /submissions by utilities outside the published plans.
-- Applied by the API (app/repository.py) before every upload, so the first upload creates it;
-- safe to run repeatedly. Reads never create it: no table just means no uploads yet.
--
-- Deliberately NOT in schema.sql and NOT referenced by any foreign key: pipeline/load.py
-- runs `TRUNCATE projects CASCADE` on every reload, and a reload of the published plans must
-- never wipe what utilities submitted. Same columns as `projects` minus the geometry, because
-- overlaps involving a submitted project are computed in Python on read (pipeline/overlap.py),
-- not stored.
CREATE TABLE IF NOT EXISTS submitted_projects (
    project_id          TEXT PRIMARY KEY,
    utility             TEXT NOT NULL,
    state               TEXT NOT NULL,
    project_name        TEXT NOT NULL,

    name_a              TEXT,
    lat_a               DOUBLE PRECISION CHECK (lat_a BETWEEN -90 AND 90),
    lon_a               DOUBLE PRECISION CHECK (lon_a BETWEEN -180 AND 180),
    name_b              TEXT,
    lat_b               DOUBLE PRECISION CHECK (lat_b BETWEEN -90 AND 90),
    lon_b               DOUBLE PRECISION CHECK (lon_b BETWEEN -180 AND 180),

    lat_center          DOUBLE PRECISION NOT NULL CHECK (lat_center BETWEEN -90 AND 90),
    lon_center          DOUBLE PRECISION NOT NULL CHECK (lon_center BETWEEN -180 AND 180),

    in_service_date     DATE NOT NULL,
    est_cost_usd        BIGINT CHECK (est_cost_usd >= 0),

    -- Always 'low' today: uploaded coordinates are the submitter's, not matched against OSM.
    location_confidence TEXT NOT NULL DEFAULT 'low'
        CHECK (location_confidence IN ('confirmed', 'low')),

    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One project name per utility, ignoring case - the same rule the API checks before insert
-- (app/submissions.py), enforced here too so two simultaneous uploads cannot both win.
CREATE UNIQUE INDEX IF NOT EXISTS submitted_projects_utility_name_idx
    ON submitted_projects (lower(utility), lower(project_name));
