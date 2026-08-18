CREATE OR REPLACE FUNCTION notify_telemetry_event()
RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('quantum_telemetry_channel', row_to_json(NEW)::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS telemetry_notify_trigger ON akashic_ledger;
CREATE TRIGGER telemetry_notify_trigger
AFTER INSERT ON akashic_ledger
FOR EACH ROW
EXECUTE FUNCTION notify_telemetry_event();
