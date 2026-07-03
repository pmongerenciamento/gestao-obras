-- Migration: 006_avatar_images_storage_policies
-- Policies de storage.objects para o bucket avatar-images (criado via
-- Admin API, fora do SQL — mesmo processo do bucket project-images, item 35
-- de docs/sessao-atual.md). Caminho dos arquivos: {user_id}/{uuid}-{nome}.
-- Mesmo padrão de policy do project-images (não registrado em migration na
-- época — corrigido aqui pra ficar reproduzível).

create policy avatar_images_insert_own on storage.objects
    for insert
    with check (
        bucket_id = 'avatar-images'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy avatar_images_update_own on storage.objects
    for update
    using (
        bucket_id = 'avatar-images'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy avatar_images_select_public on storage.objects
    for select
    using (bucket_id = 'avatar-images');
