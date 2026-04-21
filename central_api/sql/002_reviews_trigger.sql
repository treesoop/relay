-- Recompute confidence = (good + 0.5) / (good + bad + 1) and flip status='stale'
-- when we've accumulated >= 3 stale signals. Single source of truth at the DB level.

CREATE OR REPLACE FUNCTION relay_apply_review()
RETURNS TRIGGER AS $$
DECLARE
    g INT;
    b INT;
    s INT;
BEGIN
    IF NEW.signal = 'good' THEN
        UPDATE skills SET good_count = good_count + 1 WHERE id = NEW.skill_id;
    ELSIF NEW.signal = 'bad' THEN
        UPDATE skills SET bad_count = bad_count + 1 WHERE id = NEW.skill_id;
    END IF;

    SELECT good_count, bad_count INTO g, b FROM skills WHERE id = NEW.skill_id;
    UPDATE skills
       SET confidence = (g + 0.5) / GREATEST(g + b + 1, 1),
           updated_at = NOW()
     WHERE id = NEW.skill_id;

    -- Auto-stale: 3+ stale signals → status=stale
    SELECT COUNT(*) INTO s FROM reviews WHERE skill_id = NEW.skill_id AND signal = 'stale';
    IF s >= 3 THEN
        UPDATE skills SET status = 'stale' WHERE id = NEW.skill_id AND status = 'active';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reviews_apply_trigger ON reviews;
CREATE TRIGGER reviews_apply_trigger
    AFTER INSERT ON reviews
    FOR EACH ROW
    EXECUTE FUNCTION relay_apply_review();
