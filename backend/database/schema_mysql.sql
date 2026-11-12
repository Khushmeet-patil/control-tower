-- Control Tower — MySQL schema (generated; do not edit by hand).
-- Regenerate after any model change:  flask --app run schema-export
-- Alembic revision: 4c49431985a2
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
	custom_fields JSON, 
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
	CONSTRAINT fk_users_manager_id_users FOREIGN KEY(manager_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX ix_users_function_id ON users (function_id);
CREATE INDEX ix_users_is_deleted ON users (is_deleted);
CREATE INDEX ix_users_manager_id ON users (manager_id);
CREATE INDEX ix_users_tenant_id ON users (tenant_id);
CREATE INDEX ix_users_unit_id ON users (unit_id);

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

-- alembic_version (migration bookkeeping)
DROP TABLE IF EXISTS `alembic_version`;
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO alembic_version (version_num) VALUES ('4c49431985a2');

SET FOREIGN_KEY_CHECKS = 1;
