-- Existing schools remain unclassified until an administrator selects their values.
ALTER TABLE schools ADD COLUMN school_type TEXT CHECK (school_type IN ('boys','girls','kindergarten'));
ALTER TABLE schools ADD COLUMN curriculum TEXT CHECK (curriculum IN ('national','international'));
