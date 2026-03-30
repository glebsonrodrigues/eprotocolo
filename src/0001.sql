--
-- Create model Pessoa
--
CREATE TABLE `protocolos_pessoa` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `criado_em` datetime(6) NOT NULL, `atualizado_em` datetime(6) NOT NULL, `nome` varchar(50) NOT NULL, `cpf` varchar(11) NOT NULL UNIQUE, `email` varchar(254) NULL, `telefone` varchar(20) NOT NULL, `whatsapp` varchar(20) NULL, `ativo` bool NOT NULL);
--
-- Create model TipoProcesso
--
CREATE TABLE `protocolos_tipoprocesso` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nome` varchar(120) NOT NULL UNIQUE, `descricao` longtext NOT NULL, `ativo` bool NOT NULL, `criado_em` datetime(6) NOT NULL);
--
-- Create model Departamento
--
CREATE TABLE `protocolos_departamento` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `nome` varchar(150) NOT NULL, `sigla` varchar(20) NULL, `tipo` varchar(10) NOT NULL, `ativo` bool NOT NULL, `eh_protocolo_geral` bool NOT NULL, `eh_arquivo_geral` bool NOT NULL, `criado_em` datetime(6) NOT NULL, `responsavel_id` integer NULL, `substituto_id` integer NULL);
--
-- Create model DepartamentoMembro
--
CREATE TABLE `protocolos_departamentomembro` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `ativo` bool NOT NULL, `criado_em` datetime(6) NOT NULL, `departamento_id` bigint NOT NULL, `user_id` integer NOT NULL);
--
-- Create model Processo
--
CREATE TABLE `protocolos_processo` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `ano` integer UNSIGNED NOT NULL CHECK (`ano` >= 0), `numero_manual` integer UNSIGNED NOT NULL CHECK (`numero_manual` >= 0), `numero_formatado` varchar(7) NOT NULL UNIQUE, `assunto` varchar(255) NOT NULL, `descricao` longtext NULL, `prioridade` varchar(10) NOT NULL, `status` varchar(10) NOT NULL, `criado_em` datetime(6) NOT NULL, `recebido_em` datetime(6) NULL, `arquivado_em` datetime(6) NULL, `arquivado_por_id` integer NULL, `criado_por_id` integer NOT NULL, `recebido_por_id` integer NULL);
--
-- Create model MovimentacaoProcesso
--
CREATE TABLE `protocolos_movimentacaoprocesso` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `tipo_tramitacao` varchar(10) NOT NULL, `acao` varchar(12) NOT NULL, `observacao` longtext NULL, `registrado_em` datetime(6) NOT NULL, `departamento_destino_id` bigint NULL, `departamento_origem_id` bigint NOT NULL, `registrado_por_id` integer NOT NULL, `processo_id` bigint NOT NULL);
--
-- Create model Comprovante
--
CREATE TABLE `protocolos_comprovante` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `tipo` varchar(12) NOT NULL, `codigo_autenticacao` varchar(64) NOT NULL UNIQUE, `emitido_em` datetime(6) NOT NULL, `emitido_por_id` integer NOT NULL, `movimentacao_id` bigint NULL, `processo_id` bigint NOT NULL);
--
-- Create model ProcessoInteressado
--
CREATE TABLE `protocolos_processointeressado` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `papel` varchar(50) NULL, `criado_em` datetime(6) NOT NULL, `pessoa_id` bigint NOT NULL, `processo_id` bigint NOT NULL);
--
-- Add field interessados to processo
--
-- (no-op)
--
-- Add field tipo_processo to processo
--
ALTER TABLE `protocolos_processo` ADD COLUMN `tipo_processo_id` bigint NOT NULL , ADD CONSTRAINT `protocolos_processo_tipo_processo_id_ff840653_fk_protocolo` FOREIGN KEY (`tipo_processo_id`) REFERENCES `protocolos_tipoprocesso`(`id`);
--
-- Create model TramitacaoExterna
--
CREATE TABLE `protocolos_tramitacaoexterna` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `orgao_externo` varchar(150) NOT NULL, `contato_nome` varchar(120) NOT NULL, `contato_email` varchar(254) NOT NULL, `contato_telefone` varchar(30) NOT NULL, `meio_envio` varchar(20) NOT NULL, `protocolo_envio` varchar(60) NOT NULL, `enviado_em` datetime(6) NOT NULL, `prazo_retorno_em` date NULL, `status` varchar(20) NOT NULL, `recebido_em` datetime(6) NULL, `observacoes_envio` longtext NOT NULL, `observacoes_retorno` longtext NOT NULL, `anexo_envio` varchar(100) NOT NULL, `anexo_retorno` varchar(100) NOT NULL, `criado_em` datetime(6) NOT NULL, `atualizado_em` datetime(6) NOT NULL, `processo_id` bigint NOT NULL);
--
-- Create constraint uniq_departamento_nome_tipo on model departamento
--
ALTER TABLE `protocolos_departamento` ADD CONSTRAINT `uniq_departamento_nome_tipo` UNIQUE (`nome`, `tipo`);
--
-- Create constraint uniq_departamento_membro on model departamentomembro
--
ALTER TABLE `protocolos_departamentomembro` ADD CONSTRAINT `uniq_departamento_membro` UNIQUE (`departamento_id`, `user_id`);
--
-- Create constraint uniq_processo_interessado on model processointeressado
--
ALTER TABLE `protocolos_processointeressado` ADD CONSTRAINT `uniq_processo_interessado` UNIQUE (`processo_id`, `pessoa_id`);
--
-- Create constraint uniq_processo_ano_numero_manual on model processo
--
ALTER TABLE `protocolos_processo` ADD CONSTRAINT `uniq_processo_ano_numero_manual` UNIQUE (`ano`, `numero_manual`);
ALTER TABLE `protocolos_departamento` ADD CONSTRAINT `protocolos_departamento_responsavel_id_071736e4_fk_auth_user_id` FOREIGN KEY (`responsavel_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_departamento` ADD CONSTRAINT `protocolos_departamento_substituto_id_5ba4f92f_fk_auth_user_id` FOREIGN KEY (`substituto_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_departamentomembro` ADD CONSTRAINT `protocolos_departame_departamento_id_0b1e2d10_fk_protocolo` FOREIGN KEY (`departamento_id`) REFERENCES `protocolos_departamento` (`id`);
ALTER TABLE `protocolos_departamentomembro` ADD CONSTRAINT `protocolos_departamentomembro_user_id_7a750564_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_processo` ADD CONSTRAINT `protocolos_processo_arquivado_por_id_15716bac_fk_auth_user_id` FOREIGN KEY (`arquivado_por_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_processo` ADD CONSTRAINT `protocolos_processo_criado_por_id_699ab5ed_fk_auth_user_id` FOREIGN KEY (`criado_por_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_processo` ADD CONSTRAINT `protocolos_processo_recebido_por_id_318e0b55_fk_auth_user_id` FOREIGN KEY (`recebido_por_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_movimentacaoprocesso` ADD CONSTRAINT `protocolos_movimenta_departamento_destino_d31df4b6_fk_protocolo` FOREIGN KEY (`departamento_destino_id`) REFERENCES `protocolos_departamento` (`id`);
ALTER TABLE `protocolos_movimentacaoprocesso` ADD CONSTRAINT `protocolos_movimenta_departamento_origem__edc18561_fk_protocolo` FOREIGN KEY (`departamento_origem_id`) REFERENCES `protocolos_departamento` (`id`);
ALTER TABLE `protocolos_movimentacaoprocesso` ADD CONSTRAINT `protocolos_movimenta_registrado_por_id_5992491c_fk_auth_user` FOREIGN KEY (`registrado_por_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_movimentacaoprocesso` ADD CONSTRAINT `protocolos_movimenta_processo_id_5ab87a9f_fk_protocolo` FOREIGN KEY (`processo_id`) REFERENCES `protocolos_processo` (`id`);
ALTER TABLE `protocolos_comprovante` ADD CONSTRAINT `protocolos_comprovante_emitido_por_id_8a77b0c1_fk_auth_user_id` FOREIGN KEY (`emitido_por_id`) REFERENCES `auth_user` (`id`);
ALTER TABLE `protocolos_comprovante` ADD CONSTRAINT `protocolos_comprovan_movimentacao_id_ef09ad3d_fk_protocolo` FOREIGN KEY (`movimentacao_id`) REFERENCES `protocolos_movimentacaoprocesso` (`id`);
ALTER TABLE `protocolos_comprovante` ADD CONSTRAINT `protocolos_comprovan_processo_id_9af990e4_fk_protocolo` FOREIGN KEY (`processo_id`) REFERENCES `protocolos_processo` (`id`);
ALTER TABLE `protocolos_processointeressado` ADD CONSTRAINT `protocolos_processoi_pessoa_id_83cbf852_fk_protocolo` FOREIGN KEY (`pessoa_id`) REFERENCES `protocolos_pessoa` (`id`);
ALTER TABLE `protocolos_processointeressado` ADD CONSTRAINT `protocolos_processoi_processo_id_ced138b6_fk_protocolo` FOREIGN KEY (`processo_id`) REFERENCES `protocolos_processo` (`id`);
ALTER TABLE `protocolos_tramitacaoexterna` ADD CONSTRAINT `protocolos_tramitaca_processo_id_0db3955b_fk_protocolo` FOREIGN KEY (`processo_id`) REFERENCES `protocolos_processo` (`id`);
