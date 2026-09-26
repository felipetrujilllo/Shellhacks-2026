-- GridWatch schema for Tiger Data (Postgres + PostGIS).
-- Applied by pipeline/load.py before every load; safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS postgis;

-- One planned transmission project from one utility.
-- A project names two endpoints (usually substations) but only one is often locatable,
-- so the b-side columns and the line geometry are all nullable. The center is not:
-- it is what overlap detection compares, and it falls back to the single located point.
CREATE TABLE IF NOT EXISTS projects (
    project_id          TEXT PRIMARY KEY,
    utility             TEXT NOT NULL,
    state               TEXT NOT NULL,
    project_name        TEXT NOT NULL,

    name_a              TEXT,
    lat_a               DOUBLE PRECISION,
    lon_a               DOUBLE PRECISION,
    name_b              TEXT,
    lat_b               DOUBLE PRECISION,
    lon_b               DOUBLE PRECISION,

    lat_center          DOUBLE PRECISION NOT NULL,
    lon_center          DOUBLE PRECISION NOT NULL,

    in_service_date     DATE NOT NULL,
    est_cost_usd        BIGINT,  -- NULL where the utility redacts it (all of Georgia Power)

    -- 'low' means the substation match could not be confirmed against the PDF's
    -- description or county; the map should show these differently.
    location_confidence TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (location_confidence IN ('confirmed', 'low')),

    geom_center         geometry(Point, 4326) NOT NULL,
    geom_line           geometry(LineString, 4326)
);

CREATE INDEX IF NOT EXISTS projects_geom_center_idx ON projects USING GIST (geom_center);
CREATE INDEX IF NOT EXISTS projects_utility_idx ON projects (utility);

-- One flagged cross-utility pair, written by the overlap batch job.
-- A project may not overlap itself, and the same pair may only be flagged once.
CREATE TABLE IF NOT EXISTS overlaps (
    overlap_id    TEXT PRIMARY KEY,
    project_id_a  TEXT NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    project_id_b  TEXT NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,

    -- The bound is 25 inclusive, not exclusive, even though the rule is "under 25 miles".
    -- The engine gates on the full-precision haversine distance but stores it rounded to
    -- two decimals, so a pair at 24.999 mi is correctly flagged and then lands here as
    -- exactly 25.0. An exclusive bound would reject it and abort the whole load.
    distance_mi   DOUBLE PRECISION NOT NULL CHECK (distance_mi >= 0 AND distance_mi <= 25),
    time_gap_days INTEGER NOT NULL CHECK (time_gap_days >= 0),
    score         DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),

    CHECK (project_id_a <> project_id_b),
    UNIQUE (project_id_a, project_id_b)
);

CREATE INDEX IF NOT EXISTS overlaps_score_idx ON overlaps (score DESC);
