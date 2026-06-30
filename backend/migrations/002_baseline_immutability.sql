-- Migration: 002_baseline_immutability
-- Bloqueia UPDATE e DELETE em snapshots onde is_baseline = true
-- Referência: docs/referencia-projeto.md (seção 4) — "Baseline é imutável após criação"

create or replace function fn_prevent_baseline_modification()
returns trigger
language plpgsql
as $$
begin
    if OLD.is_baseline then
        raise exception 'Snapshot baseline (id=%) é imutável: UPDATE/DELETE não permitido', OLD.id;
    end if;

    if TG_OP = 'DELETE' then
        return OLD;
    end if;

    return NEW;
end;
$$;

create trigger trg_prevent_baseline_modification
    before update or delete on snapshots
    for each row
    execute function fn_prevent_baseline_modification();
