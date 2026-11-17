-- Control Tower — MySQL schema (generated; do not edit by hand).
-- Regenerate after any model change:  flask --app run schema-export
-- Alembic revision: 2f7d97b986d5
--
-- Load into an empty database:
--   CREATE DATABASE control_tower CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--   mysql -u <user> -p control_tower < schema_mysql.sql

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- audit_events
DROP TABLE IF EXISTS `audit_events`;
CREATE TABLE audit_events (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	actor_id INTEGER, 
	actor_name VARCHAR(200), 
	occurred_at DATETIME NOT NULL, 
	entity_type VARCHAR(80) NOT NULL, 
	entity_id INTEGER, 
	operation VARCHAR(40) NOT NULL, 
	field VARCHAR(120), 
	old_value TEXT, 
	new_value TEXT, 
	reason TEXT, 
	source VARCHAR(30) NOT NULL, 
	correlation_id VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id);
CREATE INDEX ix_audit_events_correlation_id ON audit_events (correlation_id);
CREATE INDEX ix_audit_events_entity_id ON audit_events (entity_id);
CREATE INDEX ix_audit_events_entity_type ON audit_events (entity_type);
CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at);
CREATE INDEX ix_audit_events_operation ON audit_events (operation);
CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id);

-- tenants
DROP TABLE IF EXISTS `tenants`;
CREATE TABLE tenants (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_tenants PRIMARY KEY (id), 
	CONSTRAINT uq_tenants_code UNIQUE (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- config_versions
DROP TABLE IF EXISTS `config_versions`;
CREATE TABLE config_versions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	is_current BOOL NOT NULL, 
	note TEXT, 
	snapshot JSON NOT NULL, 
	change_count INTEGER NOT NULL, 
	published_at DATETIME NOT NULL, 
	published_by_name VARCHAR(200), 
	restored_from_id INTEGER, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_config_versions PRIMARY KEY (id), 
	CONSTRAINT uq_config_versions_tenant_number UNIQUE (tenant_id, number), 
	CONSTRAINT fk_config_versions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_config_versions_restored_from_id_config_versions FOREIGN KEY(restored_from_id) REFERENCES config_versions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_config_versions_is_current ON config_versions (is_current);
CREATE INDEX ix_config_versions_is_deleted ON config_versions (is_deleted);
CREATE INDEX ix_config_versions_tenant_id ON config_versions (tenant_id);

-- deliveries
DROP TABLE IF EXISTS `deliveries`;
CREATE TABLE deliveries (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	channel VARCHAR(20) NOT NULL, 
	target VARCHAR(500) NOT NULL, 
	webhook_id INTEGER, 
	notification_id INTEGER, 
	event VARCHAR(80) NOT NULL, 
	subject VARCHAR(300), 
	payload JSON, 
	status VARCHAR(20) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt_at DATETIME, 
	last_error TEXT, 
	response_code INTEGER, 
	created_at DATETIME NOT NULL, 
	sent_at DATETIME, 
	CONSTRAINT pk_deliveries PRIMARY KEY (id), 
	CONSTRAINT fk_deliveries_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_deliveries_next_attempt_at ON deliveries (next_attempt_at);
CREATE INDEX ix_deliveries_status ON deliveries (status);
CREATE INDEX ix_deliveries_tenant_id ON deliveries (tenant_id);
CREATE INDEX ix_deliveries_webhook_id ON deliveries (webhook_id);

-- external_keys
DROP TABLE IF EXISTS `external_keys`;
CREATE TABLE external_keys (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	entity_type VARCHAR(40) NOT NULL, 
	external_id VARCHAR(100) NOT NULL, 
	record_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_external_keys PRIMARY KEY (id), 
	CONSTRAINT uq_external_keys_entity_id UNIQUE (tenant_id, entity_type, external_id), 
	CONSTRAINT fk_external_keys_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_external_keys_record_id ON external_keys (record_id);
CREATE INDEX ix_external_keys_tenant_id ON external_keys (tenant_id);

-- functions
DROP TABLE IF EXISTS `functions`;
CREATE TABLE functions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	code VARCHAR(50), 
	parent_id INTEGER, 
	lead_id INTEGER, 
	description TEXT, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_functions PRIMARY KEY (id), 
	CONSTRAINT uq_functions_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_functions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_functions_parent_id_functions FOREIGN KEY(parent_id) REFERENCES functions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_functions_is_deleted ON functions (is_deleted);
CREATE INDEX ix_functions_lead_id ON functions (lead_id);
CREATE INDEX ix_functions_parent_id ON functions (parent_id);
CREATE INDEX ix_functions_tenant_id ON functions (tenant_id);

-- health_rules
DROP TABLE IF EXISTS `health_rules`;
CREATE TABLE health_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	rule_type VARCHAR(40) NOT NULL, 
	params JSON, 
	outcome VARCHAR(10) NOT NULL, 
	item_type_ids JSON, 
	score INTEGER NOT NULL, 
	recommended_action TEXT, 
	escalate_to VARCHAR(30) NOT NULL, 
	description TEXT, 
	sort_order INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_health_rules PRIMARY KEY (id), 
	CONSTRAINT uq_health_rules_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_health_rules_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_health_rules_is_deleted ON health_rules (is_deleted);
CREATE INDEX ix_health_rules_tenant_id ON health_rules (tenant_id);

-- lookup_types
DROP TABLE IF EXISTS `lookup_types`;
CREATE TABLE lookup_types (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	sort_order INTEGER NOT NULL, 
	is_system BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_lookup_types PRIMARY KEY (id), 
	CONSTRAINT uq_lookup_types_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_lookup_types_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_lookup_types_is_deleted ON lookup_types (is_deleted);
CREATE INDEX ix_lookup_types_tenant_id ON lookup_types (tenant_id);

-- org_unit_types
DROP TABLE IF EXISTS `org_unit_types`;
CREATE TABLE org_unit_types (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	color VARCHAR(20), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_org_unit_types PRIMARY KEY (id), 
	CONSTRAINT uq_org_unit_types_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_org_unit_types_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_org_unit_types_is_deleted ON org_unit_types (is_deleted);
CREATE INDEX ix_org_unit_types_tenant_id ON org_unit_types (tenant_id);

-- roles
DROP TABLE IF EXISTS `roles`;
CREATE TABLE roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	scope VARCHAR(10) NOT NULL, 
	is_system BOOL NOT NULL, 
	is_default BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_roles PRIMARY KEY (id), 
	CONSTRAINT uq_roles_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_roles_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_roles_is_deleted ON roles (is_deleted);
CREATE INDEX ix_roles_tenant_id ON roles (tenant_id);

-- terms
DROP TABLE IF EXISTS `terms`;
CREATE TABLE terms (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	`key` VARCHAR(50) NOT NULL, 
	singular VARCHAR(100) NOT NULL, 
	plural VARCHAR(100) NOT NULL, 
	default_singular VARCHAR(100) NOT NULL, 
	default_plural VARCHAR(100) NOT NULL, 
	description TEXT, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_terms PRIMARY KEY (id), 
	CONSTRAINT uq_terms_tenant_key UNIQUE (tenant_id, `key`), 
	CONSTRAINT fk_terms_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_terms_is_deleted ON terms (is_deleted);
CREATE INDEX ix_terms_tenant_id ON terms (tenant_id);

-- tools
DROP TABLE IF EXISTS `tools`;
CREATE TABLE tools (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT, 
	icon VARCHAR(16), 
	kind VARCHAR(20) NOT NULL, 
	url VARCHAR(500), 
	work_item_ids JSON, 
	unit_ids JSON, 
	role_ids JSON, 
	item_type_ids JSON, 
	definition JSON, 
	context_params JSON, 
	is_active BOOL NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_tools PRIMARY KEY (id), 
	CONSTRAINT fk_tools_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_tools_is_deleted ON tools (is_deleted);
CREATE INDEX ix_tools_tenant_id ON tools (tenant_id);

-- field_definitions
DROP TABLE IF EXISTS `field_definitions`;
CREATE TABLE field_definitions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	entity_type VARCHAR(30) NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	label VARCHAR(100) NOT NULL, 
	field_type VARCHAR(20) NOT NULL, 
	lookup_type_id INTEGER, 
	help_text TEXT, 
	is_required BOOL NOT NULL, 
	is_filterable BOOL NOT NULL, 
	show_in_list BOOL NOT NULL, 
	sort_order INTEGER NOT NULL, 
	item_type_ids JSON, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_field_definitions PRIMARY KEY (id), 
	CONSTRAINT uq_field_definitions_entity_code UNIQUE (tenant_id, entity_type, code), 
	CONSTRAINT fk_field_definitions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_field_definitions_lookup_type_id_lookup_types FOREIGN KEY(lookup_type_id) REFERENCES lookup_types (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_field_definitions_entity_type ON field_definitions (entity_type);
CREATE INDEX ix_field_definitions_is_deleted ON field_definitions (is_deleted);
CREATE INDEX ix_field_definitions_tenant_id ON field_definitions (tenant_id);

-- function_closure
DROP TABLE IF EXISTS `function_closure`;
CREATE TABLE function_closure (
	ancestor_id INTEGER NOT NULL, 
	descendant_id INTEGER NOT NULL, 
	depth INTEGER NOT NULL, 
	CONSTRAINT pk_function_closure PRIMARY KEY (ancestor_id, descendant_id), 
	CONSTRAINT fk_function_closure_ancestor_id_functions FOREIGN KEY(ancestor_id) REFERENCES functions (id), 
	CONSTRAINT fk_function_closure_descendant_id_functions FOREIGN KEY(descendant_id) REFERENCES functions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_function_closure_descendant_id ON function_closure (descendant_id);

-- lookup_values
DROP TABLE IF EXISTS `lookup_values`;
CREATE TABLE lookup_values (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	lookup_type_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	label VARCHAR(100) NOT NULL, 
	color VARCHAR(7) NOT NULL, 
	description TEXT, 
	sort_order INTEGER NOT NULL, 
	is_default BOOL NOT NULL, 
	is_system BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_lookup_values PRIMARY KEY (id), 
	CONSTRAINT uq_lookup_values_type_code UNIQUE (lookup_type_id, code), 
	CONSTRAINT fk_lookup_values_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_lookup_values_lookup_type_id_lookup_types FOREIGN KEY(lookup_type_id) REFERENCES lookup_types (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_lookup_values_is_deleted ON lookup_values (is_deleted);
CREATE INDEX ix_lookup_values_lookup_type_id ON lookup_values (lookup_type_id);
CREATE INDEX ix_lookup_values_tenant_id ON lookup_values (tenant_id);

-- org_units
DROP TABLE IF EXISTS `org_units`;
CREATE TABLE org_units (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	code VARCHAR(50), 
	unit_type_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	head_id INTEGER, 
	description TEXT, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_org_units PRIMARY KEY (id), 
	CONSTRAINT uq_org_units_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_org_units_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_org_units_unit_type_id_org_unit_types FOREIGN KEY(unit_type_id) REFERENCES org_unit_types (id), 
	CONSTRAINT fk_org_units_parent_id_org_units FOREIGN KEY(parent_id) REFERENCES org_units (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_org_units_head_id ON org_units (head_id);
CREATE INDEX ix_org_units_is_deleted ON org_units (is_deleted);
CREATE INDEX ix_org_units_parent_id ON org_units (parent_id);
CREATE INDEX ix_org_units_tenant_id ON org_units (tenant_id);

-- role_permissions
DROP TABLE IF EXISTS `role_permissions`;
CREATE TABLE role_permissions (
	role_id INTEGER NOT NULL, 
	permission_code VARCHAR(80) NOT NULL, 
	CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_code), 
	CONSTRAINT fk_role_permissions_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- approval_chains
DROP TABLE IF EXISTS `approval_chains`;
CREATE TABLE approval_chains (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	item_type_ids JSON, 
	unit_id INTEGER, 
	sort_order INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_approval_chains PRIMARY KEY (id), 
	CONSTRAINT uq_approval_chains_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_approval_chains_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_approval_chains_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_approval_chains_is_deleted ON approval_chains (is_deleted);
CREATE INDEX ix_approval_chains_tenant_id ON approval_chains (tenant_id);

-- org_unit_closure
DROP TABLE IF EXISTS `org_unit_closure`;
CREATE TABLE org_unit_closure (
	ancestor_id INTEGER NOT NULL, 
	descendant_id INTEGER NOT NULL, 
	depth INTEGER NOT NULL, 
	CONSTRAINT pk_org_unit_closure PRIMARY KEY (ancestor_id, descendant_id), 
	CONSTRAINT fk_org_unit_closure_ancestor_id_org_units FOREIGN KEY(ancestor_id) REFERENCES org_units (id), 
	CONSTRAINT fk_org_unit_closure_descendant_id_org_units FOREIGN KEY(descendant_id) REFERENCES org_units (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_org_unit_closure_descendant_id ON org_unit_closure (descendant_id);

-- public_holidays
DROP TABLE IF EXISTS `public_holidays`;
CREATE TABLE public_holidays (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	holiday_date DATE NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	unit_id INTEGER, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_public_holidays PRIMARY KEY (id), 
	CONSTRAINT fk_public_holidays_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_public_holidays_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_public_holidays_holiday_date ON public_holidays (holiday_date);
CREATE INDEX ix_public_holidays_is_deleted ON public_holidays (is_deleted);
CREATE INDEX ix_public_holidays_tenant_id ON public_holidays (tenant_id);
CREATE INDEX ix_public_holidays_unit_id ON public_holidays (unit_id);

-- status_transitions
DROP TABLE IF EXISTS `status_transitions`;
CREATE TABLE status_transitions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	item_type_id INTEGER, 
	from_status_id INTEGER NOT NULL, 
	to_status_ids JSON NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_status_transitions PRIMARY KEY (id), 
	CONSTRAINT fk_status_transitions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_status_transitions_item_type_id_lookup_values FOREIGN KEY(item_type_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_status_transitions_from_status_id_lookup_values FOREIGN KEY(from_status_id) REFERENCES lookup_values (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_status_transitions_is_deleted ON status_transitions (is_deleted);
CREATE INDEX ix_status_transitions_tenant_id ON status_transitions (tenant_id);

-- users
DROP TABLE IF EXISTS `users`;
CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	job_title VARCHAR(200), 
	employee_code VARCHAR(50), 
	unit_id INTEGER, 
	function_id INTEGER, 
	manager_id INTEGER, 
	password_hash VARCHAR(255) NOT NULL, 
	is_admin BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	last_login_at DATETIME, 
	failed_logins INTEGER NOT NULL DEFAULT '0', 
	locked_until DATETIME, 
	custom_fields JSON, 
	skill_ids JSON, 
	capacity_pct INTEGER NOT NULL DEFAULT '100', 
	backlog_days INTEGER, 
	work_days JSON, 
	notification_prefs JSON, 
	entra_oid VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT uq_users_email UNIQUE (email), 
	CONSTRAINT fk_users_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_users_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id), 
	CONSTRAINT fk_users_function_id_functions FOREIGN KEY(function_id) REFERENCES functions (id), 
	CONSTRAINT fk_users_manager_id_users FOREIGN KEY(manager_id) REFERENCES users (id), 
	CONSTRAINT uq_users_entra_oid UNIQUE (entra_oid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_users_function_id ON users (function_id);
CREATE INDEX ix_users_is_deleted ON users (is_deleted);
CREATE INDEX ix_users_manager_id ON users (manager_id);
CREATE INDEX ix_users_tenant_id ON users (tenant_id);
CREATE INDEX ix_users_unit_id ON users (unit_id);

-- webhooks
DROP TABLE IF EXISTS `webhooks`;
CREATE TABLE webhooks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	format VARCHAR(20) NOT NULL, 
	events JSON NOT NULL, 
	unit_id INTEGER, 
	secret VARCHAR(80) NOT NULL, 
	description TEXT, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_webhooks PRIMARY KEY (id), 
	CONSTRAINT fk_webhooks_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_webhooks_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_webhooks_is_deleted ON webhooks (is_deleted);
CREATE INDEX ix_webhooks_tenant_id ON webhooks (tenant_id);

-- api_tokens
DROP TABLE IF EXISTS `api_tokens`;
CREATE TABLE api_tokens (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	token_prefix VARCHAR(16) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	scopes JSON NOT NULL, 
	expires_at DATETIME, 
	last_used_at DATETIME, 
	revoked_at DATETIME, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_api_tokens PRIMARY KEY (id), 
	CONSTRAINT uq_api_tokens_hash UNIQUE (token_hash), 
	CONSTRAINT fk_api_tokens_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_api_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_api_tokens_is_deleted ON api_tokens (is_deleted);
CREATE INDEX ix_api_tokens_tenant_id ON api_tokens (tenant_id);
CREATE INDEX ix_api_tokens_user_id ON api_tokens (user_id);

-- approval_steps
DROP TABLE IF EXISTS `approval_steps`;
CREATE TABLE approval_steps (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	chain_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	approver_kind VARCHAR(30) NOT NULL, 
	approver_role_id INTEGER, 
	approver_person_id INTEGER, 
	when_missing VARCHAR(10) NOT NULL, 
	checklist JSON, 
	require_evidence BOOL NOT NULL, 
	require_comment BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_approval_steps PRIMARY KEY (id), 
	CONSTRAINT fk_approval_steps_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_approval_steps_chain_id_approval_chains FOREIGN KEY(chain_id) REFERENCES approval_chains (id), 
	CONSTRAINT fk_approval_steps_approver_role_id_roles FOREIGN KEY(approver_role_id) REFERENCES roles (id), 
	CONSTRAINT fk_approval_steps_approver_person_id_users FOREIGN KEY(approver_person_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_approval_steps_chain_id ON approval_steps (chain_id);
CREATE INDEX ix_approval_steps_is_deleted ON approval_steps (is_deleted);
CREATE INDEX ix_approval_steps_tenant_id ON approval_steps (tenant_id);

-- dashboards
DROP TABLE IF EXISTS `dashboards`;
CREATE TABLE dashboards (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	is_shared BOOL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	widgets JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_dashboards PRIMARY KEY (id), 
	CONSTRAINT fk_dashboards_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_dashboards_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_dashboards_is_deleted ON dashboards (is_deleted);
CREATE INDEX ix_dashboards_owner_id ON dashboards (owner_id);
CREATE INDEX ix_dashboards_tenant_id ON dashboards (tenant_id);

-- import_batches
DROP TABLE IF EXISTS `import_batches`;
CREATE TABLE import_batches (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	entity VARCHAR(40) NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	content BLOB(5242880) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	owner_id INTEGER NOT NULL, 
	correlation_id VARCHAR(64) NOT NULL, 
	summary JSON, 
	results JSON, 
	committed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_import_batches PRIMARY KEY (id), 
	CONSTRAINT fk_import_batches_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_import_batches_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_import_batches_correlation_id ON import_batches (correlation_id);
CREATE INDEX ix_import_batches_is_deleted ON import_batches (is_deleted);
CREATE INDEX ix_import_batches_owner_id ON import_batches (owner_id);
CREATE INDEX ix_import_batches_tenant_id ON import_batches (tenant_id);

-- notifications
DROP TABLE IF EXISTS `notifications`;
CREATE TABLE notifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	body TEXT, 
	link VARCHAR(300), 
	entity_type VARCHAR(80), 
	entity_id INTEGER, 
	actor_id INTEGER, 
	read_at DATETIME, 
	dedupe_key VARCHAR(120), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_notifications PRIMARY KEY (id), 
	CONSTRAINT uq_notifications_user_dedupe UNIQUE (tenant_id, user_id, dedupe_key), 
	CONSTRAINT fk_notifications_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_notifications_is_deleted ON notifications (is_deleted);
CREATE INDEX ix_notifications_kind ON notifications (kind);
CREATE INDEX ix_notifications_read_at ON notifications (read_at);
CREATE INDEX ix_notifications_tenant_id ON notifications (tenant_id);
CREATE INDEX ix_notifications_user_id ON notifications (user_id);

-- saved_views
DROP TABLE IF EXISTS `saved_views`;
CREATE TABLE saved_views (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	page VARCHAR(30) NOT NULL, 
	filters JSON NOT NULL, 
	layout VARCHAR(10) NOT NULL, 
	is_shared BOOL NOT NULL, 
	owner_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_saved_views PRIMARY KEY (id), 
	CONSTRAINT fk_saved_views_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_saved_views_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_saved_views_is_deleted ON saved_views (is_deleted);
CREATE INDEX ix_saved_views_owner_id ON saved_views (owner_id);
CREATE INDEX ix_saved_views_page ON saved_views (page);
CREATE INDEX ix_saved_views_tenant_id ON saved_views (tenant_id);

-- scenarios
DROP TABLE IF EXISTS `scenarios`;
CREATE TABLE scenarios (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	description TEXT, 
	owner_id INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	applied_at DATETIME, 
	applied_by_id INTEGER, 
	applied_correlation_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_scenarios PRIMARY KEY (id), 
	CONSTRAINT fk_scenarios_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_scenarios_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT fk_scenarios_applied_by_id_users FOREIGN KEY(applied_by_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_scenarios_is_deleted ON scenarios (is_deleted);
CREATE INDEX ix_scenarios_owner_id ON scenarios (owner_id);
CREATE INDEX ix_scenarios_status ON scenarios (status);
CREATE INDEX ix_scenarios_tenant_id ON scenarios (tenant_id);

-- snapshots
DROP TABLE IF EXISTS `snapshots`;
CREATE TABLE snapshots (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	label VARCHAR(120) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	period VARCHAR(10), 
	as_of DATE NOT NULL, 
	taken_at DATETIME NOT NULL, 
	taken_by_id INTEGER, 
	item_count INTEGER NOT NULL, 
	notes TEXT, 
	status VARCHAR(20) NOT NULL, 
	approved_by_id INTEGER, 
	approved_at DATETIME, 
	is_baseline BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_snapshots PRIMARY KEY (id), 
	CONSTRAINT uq_snapshots_tenant_period UNIQUE (tenant_id, period), 
	CONSTRAINT fk_snapshots_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_snapshots_taken_by_id_users FOREIGN KEY(taken_by_id) REFERENCES users (id), 
	CONSTRAINT fk_snapshots_approved_by_id_users FOREIGN KEY(approved_by_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_snapshots_as_of ON snapshots (as_of);
CREATE INDEX ix_snapshots_is_deleted ON snapshots (is_deleted);
CREATE INDEX ix_snapshots_tenant_id ON snapshots (tenant_id);

-- time_off
DROP TABLE IF EXISTS `time_off`;
CREATE TABLE time_off (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	person_id INTEGER NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	kind_id INTEGER, 
	note VARCHAR(300), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_time_off PRIMARY KEY (id), 
	CONSTRAINT fk_time_off_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_time_off_person_id_users FOREIGN KEY(person_id) REFERENCES users (id), 
	CONSTRAINT fk_time_off_kind_id_lookup_values FOREIGN KEY(kind_id) REFERENCES lookup_values (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_time_off_end_date ON time_off (end_date);
CREATE INDEX ix_time_off_is_deleted ON time_off (is_deleted);
CREATE INDEX ix_time_off_person_id ON time_off (person_id);
CREATE INDEX ix_time_off_start_date ON time_off (start_date);
CREATE INDEX ix_time_off_tenant_id ON time_off (tenant_id);

-- user_roles
DROP TABLE IF EXISTS `user_roles`;
CREATE TABLE user_roles (
	user_id INTEGER NOT NULL, 
	role_id INTEGER NOT NULL, 
	CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id), 
	CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id), 
	CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);

-- work_items
DROP TABLE IF EXISTS `work_items`;
CREATE TABLE work_items (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	description TEXT, 
	item_type_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	status_id INTEGER, 
	priority_id INTEGER, 
	category_id INTEGER, 
	action_type_id INTEGER, 
	severity_id INTEGER, 
	unit_id INTEGER, 
	function_id INTEGER, 
	accountable_id INTEGER NOT NULL, 
	owner_overridden BOOL NOT NULL, 
	planned_start DATE, 
	planned_end DATE, 
	actual_start DATE, 
	actual_end DATE, 
	progress_manual INTEGER, 
	objective TEXT, 
	risks TEXT, 
	remarks TEXT, 
	evidence_url VARCHAR(500), 
	weight INTEGER NOT NULL DEFAULT '1', 
	approval_status VARCHAR(20), 
	approved_at DATETIME, 
	custom_fields JSON, 
	adoption_stage_ids JSON, 
	adoption_evidence VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_work_items PRIMARY KEY (id), 
	CONSTRAINT uq_work_items_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_work_items_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_work_items_item_type_id_lookup_values FOREIGN KEY(item_type_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_parent_id_work_items FOREIGN KEY(parent_id) REFERENCES work_items (id), 
	CONSTRAINT fk_work_items_status_id_lookup_values FOREIGN KEY(status_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_priority_id_lookup_values FOREIGN KEY(priority_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_category_id_lookup_values FOREIGN KEY(category_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_action_type_id_lookup_values FOREIGN KEY(action_type_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_severity_id_lookup_values FOREIGN KEY(severity_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_work_items_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id), 
	CONSTRAINT fk_work_items_function_id_functions FOREIGN KEY(function_id) REFERENCES functions (id), 
	CONSTRAINT fk_work_items_accountable_id_users FOREIGN KEY(accountable_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_work_items_accountable_id ON work_items (accountable_id);
CREATE INDEX ix_work_items_approval_status ON work_items (approval_status);
CREATE INDEX ix_work_items_category_id ON work_items (category_id);
CREATE INDEX ix_work_items_function_id ON work_items (function_id);
CREATE INDEX ix_work_items_is_deleted ON work_items (is_deleted);
CREATE INDEX ix_work_items_item_type_id ON work_items (item_type_id);
CREATE INDEX ix_work_items_parent_id ON work_items (parent_id);
CREATE INDEX ix_work_items_planned_end ON work_items (planned_end);
CREATE INDEX ix_work_items_priority_id ON work_items (priority_id);
CREATE INDEX ix_work_items_status_id ON work_items (status_id);
CREATE INDEX ix_work_items_tenant_id ON work_items (tenant_id);
CREATE INDEX ix_work_items_unit_id ON work_items (unit_id);

-- approval_requests
DROP TABLE IF EXISTS `approval_requests`;
CREATE TABLE approval_requests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	work_item_id INTEGER NOT NULL, 
	chain_id INTEGER, 
	chain_name VARCHAR(100) NOT NULL, 
	steps JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	current_step INTEGER NOT NULL, 
	current_approver_id INTEGER, 
	current_role_id INTEGER, 
	waiting_note TEXT, 
	submitted_by_id INTEGER, 
	submitted_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_approval_requests PRIMARY KEY (id), 
	CONSTRAINT fk_approval_requests_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_approval_requests_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_approval_requests_chain_id_approval_chains FOREIGN KEY(chain_id) REFERENCES approval_chains (id), 
	CONSTRAINT fk_approval_requests_current_approver_id_users FOREIGN KEY(current_approver_id) REFERENCES users (id), 
	CONSTRAINT fk_approval_requests_current_role_id_roles FOREIGN KEY(current_role_id) REFERENCES roles (id), 
	CONSTRAINT fk_approval_requests_submitted_by_id_users FOREIGN KEY(submitted_by_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_approval_requests_current_approver_id ON approval_requests (current_approver_id);
CREATE INDEX ix_approval_requests_current_role_id ON approval_requests (current_role_id);
CREATE INDEX ix_approval_requests_is_deleted ON approval_requests (is_deleted);
CREATE INDEX ix_approval_requests_status ON approval_requests (status);
CREATE INDEX ix_approval_requests_submitted_by_id ON approval_requests (submitted_by_id);
CREATE INDEX ix_approval_requests_tenant_id ON approval_requests (tenant_id);
CREATE INDEX ix_approval_requests_work_item_id ON approval_requests (work_item_id);

-- assignments
DROP TABLE IF EXISTS `assignments`;
CREATE TABLE assignments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	work_item_id INTEGER NOT NULL, 
	person_id INTEGER NOT NULL, 
	role_id INTEGER, 
	allocation_pct INTEGER NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	duties TEXT, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_assignments PRIMARY KEY (id), 
	CONSTRAINT fk_assignments_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_assignments_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_assignments_person_id_users FOREIGN KEY(person_id) REFERENCES users (id), 
	CONSTRAINT fk_assignments_role_id_lookup_values FOREIGN KEY(role_id) REFERENCES lookup_values (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_assignments_is_deleted ON assignments (is_deleted);
CREATE INDEX ix_assignments_person_id ON assignments (person_id);
CREATE INDEX ix_assignments_tenant_id ON assignments (tenant_id);
CREATE INDEX ix_assignments_work_item_id ON assignments (work_item_id);

-- demand_requests
DROP TABLE IF EXISTS `demand_requests`;
CREATE TABLE demand_requests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	description TEXT, 
	requester_id INTEGER NOT NULL, 
	sponsor VARCHAR(200), 
	business_value TEXT, 
	urgency_id INTEGER, 
	priority_id INTEGER, 
	effort_pct INTEGER, 
	requested_on DATE NOT NULL, 
	needed_by DATE, 
	dependencies TEXT, 
	remarks TEXT, 
	unit_id INTEGER NOT NULL, 
	decision_id INTEGER, 
	decision_note TEXT, 
	decided_by_id INTEGER, 
	decided_at DATETIME, 
	work_item_id INTEGER, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_demand_requests PRIMARY KEY (id), 
	CONSTRAINT uq_demand_requests_tenant_code UNIQUE (tenant_id, code), 
	CONSTRAINT fk_demand_requests_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_demand_requests_requester_id_users FOREIGN KEY(requester_id) REFERENCES users (id), 
	CONSTRAINT fk_demand_requests_urgency_id_lookup_values FOREIGN KEY(urgency_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_demand_requests_priority_id_lookup_values FOREIGN KEY(priority_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_demand_requests_unit_id_org_units FOREIGN KEY(unit_id) REFERENCES org_units (id), 
	CONSTRAINT fk_demand_requests_decision_id_lookup_values FOREIGN KEY(decision_id) REFERENCES lookup_values (id), 
	CONSTRAINT fk_demand_requests_decided_by_id_users FOREIGN KEY(decided_by_id) REFERENCES users (id), 
	CONSTRAINT fk_demand_requests_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_demand_requests_decision_id ON demand_requests (decision_id);
CREATE INDEX ix_demand_requests_is_deleted ON demand_requests (is_deleted);
CREATE INDEX ix_demand_requests_requester_id ON demand_requests (requester_id);
CREATE INDEX ix_demand_requests_tenant_id ON demand_requests (tenant_id);
CREATE INDEX ix_demand_requests_unit_id ON demand_requests (unit_id);

-- health_watch
DROP TABLE IF EXISTS `health_watch`;
CREATE TABLE health_watch (
	work_item_id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	health VARCHAR(20), 
	seen_at DATETIME NOT NULL, 
	CONSTRAINT pk_health_watch PRIMARY KEY (work_item_id), 
	CONSTRAINT fk_health_watch_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_health_watch_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_health_watch_tenant_id ON health_watch (tenant_id);

-- presentations
DROP TABLE IF EXISTS `presentations`;
CREATE TABLE presentations (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT, 
	owner_id INTEGER NOT NULL, 
	is_shared BOOL NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	snapshot_id INTEGER, 
	pages JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	published_at DATETIME, 
	published_by_id INTEGER, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_presentations PRIMARY KEY (id), 
	CONSTRAINT fk_presentations_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_presentations_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT fk_presentations_snapshot_id_snapshots FOREIGN KEY(snapshot_id) REFERENCES snapshots (id), 
	CONSTRAINT fk_presentations_published_by_id_users FOREIGN KEY(published_by_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_presentations_is_deleted ON presentations (is_deleted);
CREATE INDEX ix_presentations_owner_id ON presentations (owner_id);
CREATE INDEX ix_presentations_snapshot_id ON presentations (snapshot_id);
CREATE INDEX ix_presentations_tenant_id ON presentations (tenant_id);

-- scenario_changes
DROP TABLE IF EXISTS `scenario_changes`;
CREATE TABLE scenario_changes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	scenario_id INTEGER NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	target_id INTEGER, 
	work_item_id INTEGER, 
	changes JSON, 
	base_version INTEGER, 
	note VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_scenario_changes PRIMARY KEY (id), 
	CONSTRAINT fk_scenario_changes_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_scenario_changes_scenario_id_scenarios FOREIGN KEY(scenario_id) REFERENCES scenarios (id), 
	CONSTRAINT fk_scenario_changes_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_scenario_changes_is_deleted ON scenario_changes (is_deleted);
CREATE INDEX ix_scenario_changes_scenario_id ON scenario_changes (scenario_id);
CREATE INDEX ix_scenario_changes_tenant_id ON scenario_changes (tenant_id);
CREATE INDEX ix_scenario_changes_work_item_id ON scenario_changes (work_item_id);

-- snapshot_items
DROP TABLE IF EXISTS `snapshot_items`;
CREATE TABLE snapshot_items (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	snapshot_id INTEGER NOT NULL, 
	work_item_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	code VARCHAR(30) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	item_type_id INTEGER, 
	status_id INTEGER, 
	priority_id INTEGER, 
	category_id INTEGER, 
	action_type_id INTEGER, 
	severity_id INTEGER, 
	unit_id INTEGER, 
	unit_name VARCHAR(200), 
	unit_path JSON, 
	function_id INTEGER, 
	accountable_id INTEGER, 
	accountable_name VARCHAR(200), 
	responsible_ids JSON, 
	assignee_ids JSON, 
	planned_start DATE, 
	planned_end DATE, 
	actual_end DATE, 
	progress INTEGER NOT NULL, 
	weight INTEGER NOT NULL, 
	health VARCHAR(20), 
	health_value_id INTEGER, 
	health_reason TEXT, 
	is_open BOOL NOT NULL, 
	is_overdue BOOL NOT NULL, 
	approval_status VARCHAR(20), 
	custom_fields JSON, 
	CONSTRAINT pk_snapshot_items PRIMARY KEY (id), 
	CONSTRAINT fk_snapshot_items_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_snapshot_items_snapshot_id_snapshots FOREIGN KEY(snapshot_id) REFERENCES snapshots (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_snapshot_items_snapshot_id ON snapshot_items (snapshot_id);
CREATE INDEX ix_snapshot_items_tenant_id ON snapshot_items (tenant_id);
CREATE INDEX ix_snapshot_items_work_item_id ON snapshot_items (work_item_id);

-- snapshot_people
DROP TABLE IF EXISTS `snapshot_people`;
CREATE TABLE snapshot_people (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	snapshot_id INTEGER NOT NULL, 
	person_id INTEGER NOT NULL, 
	full_name VARCHAR(200) NOT NULL, 
	job_title VARCHAR(200), 
	unit_id INTEGER, 
	unit_name VARCHAR(200), 
	unit_path JSON, 
	function_name VARCHAR(200), 
	skill_ids JSON, 
	capacity_pct INTEGER NOT NULL, 
	available_pct INTEGER NOT NULL, 
	usable_pct INTEGER NOT NULL, 
	load_pct INTEGER NOT NULL, 
	free_pct INTEGER NOT NULL, 
	status VARCHAR(20), 
	allocated_items INTEGER NOT NULL, 
	buffer_pct INTEGER NOT NULL, 
	CONSTRAINT pk_snapshot_people PRIMARY KEY (id), 
	CONSTRAINT fk_snapshot_people_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_snapshot_people_snapshot_id_snapshots FOREIGN KEY(snapshot_id) REFERENCES snapshots (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_snapshot_people_person_id ON snapshot_people (person_id);
CREATE INDEX ix_snapshot_people_snapshot_id ON snapshot_people (snapshot_id);
CREATE INDEX ix_snapshot_people_tenant_id ON snapshot_people (tenant_id);

-- tool_responses
DROP TABLE IF EXISTS `tool_responses`;
CREATE TABLE tool_responses (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	tool_id INTEGER NOT NULL, 
	work_item_id INTEGER NOT NULL, 
	answers JSON, 
	notes TEXT, 
	score_pct INTEGER NOT NULL, 
	passed BOOL NOT NULL, 
	submitted_by_id INTEGER, 
	submitted_at DATETIME, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_tool_responses PRIMARY KEY (id), 
	CONSTRAINT uq_tool_responses_tool_item UNIQUE (tenant_id, tool_id, work_item_id), 
	CONSTRAINT fk_tool_responses_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_tool_responses_tool_id_tools FOREIGN KEY(tool_id) REFERENCES tools (id), 
	CONSTRAINT fk_tool_responses_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_tool_responses_submitted_by_id_users FOREIGN KEY(submitted_by_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_tool_responses_is_deleted ON tool_responses (is_deleted);
CREATE INDEX ix_tool_responses_tenant_id ON tool_responses (tenant_id);
CREATE INDEX ix_tool_responses_tool_id ON tool_responses (tool_id);
CREATE INDEX ix_tool_responses_work_item_id ON tool_responses (work_item_id);

-- work_item_closure
DROP TABLE IF EXISTS `work_item_closure`;
CREATE TABLE work_item_closure (
	ancestor_id INTEGER NOT NULL, 
	descendant_id INTEGER NOT NULL, 
	depth INTEGER NOT NULL, 
	CONSTRAINT pk_work_item_closure PRIMARY KEY (ancestor_id, descendant_id), 
	CONSTRAINT fk_work_item_closure_ancestor_id_work_items FOREIGN KEY(ancestor_id) REFERENCES work_items (id), 
	CONSTRAINT fk_work_item_closure_descendant_id_work_items FOREIGN KEY(descendant_id) REFERENCES work_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_work_item_closure_descendant_id ON work_item_closure (descendant_id);

-- work_item_dependencies
DROP TABLE IF EXISTS `work_item_dependencies`;
CREATE TABLE work_item_dependencies (
	work_item_id INTEGER NOT NULL, 
	depends_on_id INTEGER NOT NULL, 
	CONSTRAINT pk_work_item_dependencies PRIMARY KEY (work_item_id, depends_on_id), 
	CONSTRAINT fk_work_item_dependencies_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_work_item_dependencies_depends_on_id_work_items FOREIGN KEY(depends_on_id) REFERENCES work_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_work_item_dependencies_depends_on_id ON work_item_dependencies (depends_on_id);

-- work_item_responsibles
DROP TABLE IF EXISTS `work_item_responsibles`;
CREATE TABLE work_item_responsibles (
	work_item_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	CONSTRAINT pk_work_item_responsibles PRIMARY KEY (work_item_id, user_id), 
	CONSTRAINT fk_work_item_responsibles_work_item_id_work_items FOREIGN KEY(work_item_id) REFERENCES work_items (id), 
	CONSTRAINT fk_work_item_responsibles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_work_item_responsibles_user_id ON work_item_responsibles (user_id);

-- work_templates
DROP TABLE IF EXISTS `work_templates`;
CREATE TABLE work_templates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	description TEXT, 
	owner_id INTEGER NOT NULL, 
	is_shared BOOL NOT NULL, 
	structure JSON NOT NULL, 
	node_count INTEGER NOT NULL, 
	source_item_id INTEGER, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_work_templates PRIMARY KEY (id), 
	CONSTRAINT fk_work_templates_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_work_templates_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id), 
	CONSTRAINT fk_work_templates_source_item_id_work_items FOREIGN KEY(source_item_id) REFERENCES work_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_work_templates_is_deleted ON work_templates (is_deleted);
CREATE INDEX ix_work_templates_owner_id ON work_templates (owner_id);
CREATE INDEX ix_work_templates_tenant_id ON work_templates (tenant_id);

-- approval_decisions
DROP TABLE IF EXISTS `approval_decisions`;
CREATE TABLE approval_decisions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tenant_id INTEGER NOT NULL, 
	request_id INTEGER NOT NULL, 
	step_index INTEGER NOT NULL, 
	step_name VARCHAR(100) NOT NULL, 
	decision VARCHAR(20) NOT NULL, 
	approver_id INTEGER, 
	comment TEXT, 
	checklist JSON, 
	decided_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	created_by_id INTEGER, 
	updated_at DATETIME NOT NULL, 
	updated_by_id INTEGER, 
	version INTEGER NOT NULL, 
	is_deleted BOOL NOT NULL, 
	deleted_at DATETIME, 
	CONSTRAINT pk_approval_decisions PRIMARY KEY (id), 
	CONSTRAINT fk_approval_decisions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	CONSTRAINT fk_approval_decisions_request_id_approval_requests FOREIGN KEY(request_id) REFERENCES approval_requests (id), 
	CONSTRAINT fk_approval_decisions_approver_id_users FOREIGN KEY(approver_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_approval_decisions_approver_id ON approval_decisions (approver_id);
CREATE INDEX ix_approval_decisions_is_deleted ON approval_decisions (is_deleted);
CREATE INDEX ix_approval_decisions_request_id ON approval_decisions (request_id);
CREATE INDEX ix_approval_decisions_tenant_id ON approval_decisions (tenant_id);

-- alembic_version (migration bookkeeping)
DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO alembic_version (version_num) VALUES ('2f7d97b986d5');

SET FOREIGN_KEY_CHECKS = 1;
