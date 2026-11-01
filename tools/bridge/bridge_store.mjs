// 桥持久化存储层（RE-B1-桥持久化.md §3 设计落码）。
// F2：每实例一分库文件 bridge-{port}.db（BRIDGE_PORT 隔离，双进程永不共库）；
// 打开/迁移失败直接抛（fail-closed，桥启动失败），不空库假装正常。
// 表：schema_migration（账本，重启不重放）/ sessions（索引+水位+busy+last_command_id）/
//     session_rows（row_json=整行对象，恢复行字段零丢失 F4）/ command_receipts（仅终态，F1①）。
import { createRequire } from "node:module";
import { createHmac, randomBytes } from "node:crypto";
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
// 与 bridge_host.mjs 同款手法：避免构建器把 node:sqlite 改写成不存在的 npm sqlite 包。
const { DatabaseSync } = createRequire(import.meta.url)("node:sqlite");
// 功能 #6 材料上传解析（RE-6 §3）：DDL 单源在 material_service.mjs（迁移与合成自测共用同一份，
// 防 DDL 两处漂移）。
import { MATERIALS_DDL, MATERIALS_DDL_FTS_TRIGRAM, MATERIALS_DDL_FTS_FALLBACK, BRIDGE_ATTACHMENTS_PRODUCER_DDL, createMaterialDao } from "./material_service.mjs";
import { EDISC_DDL, EDISC_REVIEW_DDL, createEdiscDao } from "./edisc_service.mjs";
// 功能 #32 整理与尽调（RE-32 §3）：看板/成果版本/字段模板/台账/清单/沿革六表，DDL 单源在 diligence_service.mjs（迁移 0024）。
import { DILIGENCE_DDL, createDiligenceDao } from "./diligence_service.mjs";
// 【#21 安全层】工具决策审计（RE-21 增补）：DDL 单源在 tool_audit_service.mjs（迁移 0021）。
import { TOOL_AUDITS_DDL, createToolAuditService } from "./tool_audit_service.mjs";
// 功能 #35 Flow 工作流消费侧（RE-35 §3）：引擎/Studio/AI-run 持久化面，DDL 单源在 flow_engine_service.mjs（迁移 0022）。
import { FLOW_ENGINE_DDL } from "./flow_engine_service.mjs";

const MIGRATIONS = [
  { id: "0001_initial", sql: `
      CREATE TABLE IF NOT EXISTS sessions (
        workspace_key TEXT NOT NULL,
        session_id TEXT NOT NULL,
        oc28_id TEXT,
        title TEXT NOT NULL DEFAULT '',
        project_id TEXT,
        workspace_path TEXT,
        last_outcome TEXT,
        phase TEXT NOT NULL DEFAULT 'draft',
        seq INTEGER NOT NULL DEFAULT 0,
        row_seq INTEGER NOT NULL DEFAULT 0,
        busy INTEGER NOT NULL DEFAULT 0,
        last_command_id TEXT,
        meta_json TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        deleted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (workspace_key, session_id)
      );
      CREATE INDEX IF NOT EXISTS idx_sessions_workspace_updated
        ON sessions (workspace_key, updated_at DESC) WHERE deleted = 0;

      CREATE TABLE IF NOT EXISTS session_rows (
        workspace_key TEXT NOT NULL,
        session_id TEXT NOT NULL,
        row_seq INTEGER NOT NULL,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        text TEXT NOT NULL DEFAULT '',
        source_command_id TEXT,
        row_json TEXT NOT NULL,
        PRIMARY KEY (workspace_key, session_id, row_seq)
      );

      CREATE TABLE IF NOT EXISTS command_receipts (
        workspace_key TEXT NOT NULL,
        command_id TEXT NOT NULL,
        session_id TEXT,
        ack_json TEXT NOT NULL,
        outcome TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (workspace_key, command_id)
      );
  ` },
  { id: "0003_document_fts_v2", sql: `
      -- RE-15 v2：0002 的独立 contentful FTS5 表对 UNINDEXED 列谓词不可靠（实测 = 可用、
      -- LIKE 静默失配、MATCH+UNINDEXED 过滤不稳定）——改教科书外部内容模式：
      -- 普通表为权威副本，触发器同步 external-content FTS5，查询经 JOIN 回普通表过滤。
      DROP TABLE IF EXISTS document_chunks_fts;
      CREATE TABLE IF NOT EXISTS document_chunks (
        workspace_key TEXT NOT NULL,
        session_id TEXT NOT NULL,
        chunk_id TEXT NOT NULL,
        source_label TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL DEFAULT 0,
        text TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (workspace_key, session_id, chunk_id)
      );
      CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
        text, content='document_chunks', content_rowid='rowid', tokenize='trigram'
      );
      CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
        INSERT INTO document_chunks_fts(rowid, text) VALUES (new.rowid, new.text);
      END;
      CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
        INSERT INTO document_chunks_fts(document_chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
      END;
      CREATE TRIGGER IF NOT EXISTS document_chunks_au AFTER UPDATE ON document_chunks BEGIN
        INSERT INTO document_chunks_fts(document_chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
        INSERT INTO document_chunks_fts(rowid, text) VALUES (new.rowid, new.text);
      END;
      -- 回填既有完成行（userInput 全部 / assistantText complete），PRIMARY KEY 幂等
      INSERT OR IGNORE INTO document_chunks (workspace_key, session_id, chunk_id, source_label, kind, created_at, text)
      SELECT r.workspace_key, r.session_id, r.row_seq, r.kind, r.kind, 0, json_extract(r.row_json, '$.text')
      FROM session_rows r
      WHERE r.kind IN ('userInput', 'assistantText')
        AND (r.kind <> 'assistantText' OR r.state = 'complete');
  ` },
  { id: "0004_redline", sql: `
      -- 功能 #11 Word 红线改稿（施工单-03 任务一）：改稿记录与修订项落桥同库（重启不丢）。
      CREATE TABLE IF NOT EXISTS redline_revisions (
        workspace_key TEXT NOT NULL,
        revision_id TEXT NOT NULL,
        material_name TEXT NOT NULL,
        instruction TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'revising',
        original_text TEXT NOT NULL DEFAULT '',
        revised_text TEXT NOT NULL DEFAULT '',
        final_text TEXT,
        final_path TEXT,
        error TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (workspace_key, revision_id)
      );
      CREATE TABLE IF NOT EXISTS redline_items (
        workspace_key TEXT NOT NULL,
        revision_id TEXT NOT NULL,
        item_idx INTEGER NOT NULL,
        type TEXT NOT NULL,
        a_start INTEGER NOT NULL DEFAULT 0,
        a_count INTEGER NOT NULL DEFAULT 0,
        b_start INTEGER NOT NULL DEFAULT 0,
        b_count INTEGER NOT NULL DEFAULT 0,
        old_text TEXT NOT NULL DEFAULT '',
        new_text TEXT NOT NULL DEFAULT '',
        decision TEXT NOT NULL DEFAULT 'pending',
        PRIMARY KEY (workspace_key, revision_id, item_idx)
      );
  ` },
  { id: "0005_case_board", sql: `
      -- 【步骤4·案件族底座】MatterLite 桥内轻量案件表（RE-3-案件看板.md 实现规格 §3.2 落码）。
      -- ⚠ 过渡态：三表只是看板数据的临时真源——决策台账 2026-10-27 03:35：MatterStore 解挂后
      -- 翻牌真源、本轻量表退役（届时数据迁出真源后删表）。
      -- 字段口径（§3.6 确定性纪律）：日期一律 YYYY-MM-DD 字符串（后端强校验）；金额整型分禁浮点；
      -- workflow_status 存 11 档枚举固定字符串、NULL=自动推断（推断纯函数在 UI 侧，§3.4-1）；
      -- overrides_json 只存人工覆盖层（§3.4-3），#4/#6 派生数据不建表、原值永远可还原。
      CREATE TABLE IF NOT EXISTS case_board_cases (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        cause TEXT NOT NULL DEFAULT '',
        case_no TEXT NOT NULL DEFAULT '',
        court TEXT NOT NULL DEFAULT '',
        court_type TEXT NOT NULL DEFAULT '法院',
        claim_amount_cents INTEGER NOT NULL DEFAULT 0,
        plaintiffs_json TEXT NOT NULL DEFAULT '[]',
        defendants_json TEXT NOT NULL DEFAULT '[]',
        judges_json TEXT NOT NULL DEFAULT '[]',
        workflow_status TEXT,
        workflow_locked INTEGER NOT NULL DEFAULT 0,
        overrides_json TEXT NOT NULL DEFAULT '{}',
        sort_order INTEGER,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS case_board_todos (
        id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        title TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        done_at TEXT,
        due_date TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES case_board_cases(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS case_board_events (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        title TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL
      );
  ` },
  { id: "0007_board_schedule_face", sql: `
      -- 【步骤4·#3 看板日历面】case_board_events 增列（RE-3-案件看板.md 对拍行 80/81/83/85/86 字段面落列）。
      -- §3.2 原四列不动；增列语义：
      --   case_id 可空=可选关联案件（对拍行 80「关联案件」；SQLite ALTER 无法带 FK——案件删除时
      --   由桥面显式置空 store.clearEventCaseLink，待办仍走 0005 的 FK 级联）；
      --   kind=日程三分类（hearing/deadline/schedule，对拍行 81 自定词表，默认 schedule）；
      --   start_at/end_at=HH:MM（对拍行 80 默认 10:00-11:00，NULL=date-only 行按当日 09:00 归一开火，§3.4-5）；
      --   trip=出行项可选字段（对拍行 83：出行项做可选字段不做独立规划面）；
      --   remind/remind_minutes=提醒引擎数据面（对拍行 85：逐条开关+提前分钟，默认 30）。
      -- ⚠ 基表仍为过渡态（0005_case_board 注：MatterStore 解挂后翻牌真源、轻量表退役）。
      ALTER TABLE case_board_events ADD COLUMN case_id TEXT;
      ALTER TABLE case_board_events ADD COLUMN kind TEXT NOT NULL DEFAULT 'schedule';
      ALTER TABLE case_board_events ADD COLUMN location TEXT NOT NULL DEFAULT '';
      ALTER TABLE case_board_events ADD COLUMN start_at TEXT;
      ALTER TABLE case_board_events ADD COLUMN end_at TEXT;
      ALTER TABLE case_board_events ADD COLUMN trip TEXT;
      ALTER TABLE case_board_events ADD COLUMN remind INTEGER NOT NULL DEFAULT 0;
      ALTER TABLE case_board_events ADD COLUMN remind_minutes INTEGER NOT NULL DEFAULT 30;
  ` },
  { id: "0006_case_graph", sql: `
      -- 功能 #19 轻量知识图谱（步骤4·RE-19）：graph 文档式 JSON 一图一行（不建三表，RE-19 §3）。
      -- 案件 id 现阶段为工作区单案占位（MatterLite/#3 落地后即真实案件 id）；乐观锁版本在 revision 列。
      CREATE TABLE IF NOT EXISTS case_graphs (
        workspace_key TEXT NOT NULL,
        case_id TEXT NOT NULL,
        graph_json TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (workspace_key, case_id)
      );
  ` },
  { id: "0005_onboarding", sql: `
      -- 功能 #29 新手引导与产品指引（RE-29 §3 数据模型）：三键 KV + 演示台账 + 演示集业务表。
      -- 生产启动路径绝不预置数据（seed:false 等量语义）：演示内容只从向导明确选择进入。
      CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS onboarding_demo_ledger (
        version TEXT PRIMARY KEY,
        imported_at TEXT DEFAULT (datetime('now'))
      );
      -- 演示集业务表（全部合成虚构数据；卫检四表=cases/documents/clients/schedule_events）
      CREATE TABLE IF NOT EXISTS demo_cases (
        case_id TEXT PRIMARY KEY, name TEXT NOT NULL, case_no TEXT NOT NULL DEFAULT '',
        case_type TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT '',
        client_id TEXT, created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_stage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
        stage TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', happened_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_clients (
        client_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '',
        contact TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_documents (
        doc_id TEXT PRIMARY KEY, case_id TEXT, title TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'final',
        created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_schedule_events (
        event_id TEXT PRIMARY KEY, case_id TEXT, title TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'work', due_at INTEGER NOT NULL, created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_tasks (
        task_id TEXT PRIMARY KEY, case_id TEXT, title TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual', done INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_parties (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
        name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', client_id TEXT
      );
      CREATE TABLE IF NOT EXISTS demo_evidence (
        evidence_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, title TEXT NOT NULL,
        tag TEXT NOT NULL DEFAULT '辅助', created_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS demo_strategies (
        strategy_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
        suggestions_json TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL DEFAULT 0
      );
  ` },
  { id: "0008_audit_log", sql: `
      -- 功能 #30 安全审计中心（RE-30 §3.2 数据模型，DDL 等量同构八字段）。
      -- 只追加（append-only）：无删改路径、无清空/导出/分页；链函数在 audit_service.mjs
      -- 单实例共享（对拍 52），密钥落 app_meta 键 audit.hmac（fail-closed 语义见该文件头注）。
      CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        ts TEXT,
        actor TEXT,
        action TEXT,
        target TEXT,
        detail TEXT,
        prev_hash TEXT,
        hash TEXT
      );
  ` },
  { id: "0009_kb", sql: `
      -- 功能 #20 所内知识问答（RE-20 §3 数据模型）：文集(=文件夹)/文档/块/FTS/账本五件。
      -- 与 0003 同款教科书外部内容模式（普通表权威副本+触发器同步 external-content FTS5，
      -- 查询经 JOIN 回普通表过滤——UNINDEXED 谓词直滤不可靠，0003 注有实测）。
      -- FTS 只收 content 一列（title/rel_path/category 等过滤与展示全走 JOIN 后普通表列，
      -- 避免外部内容表多列不同步的 delete 语义坑）；块删除走文档外键级联+blocks_ad 同步。
      CREATE TABLE IF NOT EXISTS kb_collections (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS kb_documents (
        id TEXT PRIMARY KEY,
        collection_path TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        rel_path TEXT NOT NULL UNIQUE,
        ext TEXT NOT NULL DEFAULT '',
        size_bytes INTEGER NOT NULL DEFAULT 0,
        mtime_ms INTEGER NOT NULL DEFAULT 0,
        content_hash TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT '',
        tags_json TEXT NOT NULL DEFAULT '[]',
        keywords_json TEXT NOT NULL DEFAULT '[]',
        indexed_at INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS kb_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        heading_path_json TEXT NOT NULL DEFAULT '[]',
        article_number TEXT,
        content TEXT NOT NULL DEFAULT '',
        char_start INTEGER NOT NULL DEFAULT 0,
        char_end INTEGER NOT NULL DEFAULT 0,
        chunk_hash TEXT NOT NULL DEFAULT '',
        provenance_id TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (document_id) REFERENCES kb_documents(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS kb_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
  ` },
  { id: "0009_kb_fts", sql: `
      -- FTS5 trigram 优先（RE-20 §3：失败降级 unicode61，由迁移运行器 fallbackSql 承接）；
      -- 只收 content 一列（title/rel_path/category 过滤与展示全走 JOIN 后普通表列，
      -- 避免外部内容表多列不同步的 delete 语义坑）；块删除走外键级联+触发器同步。
      CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
        content, content='kb_chunks', content_rowid='rowid', tokenize='trigram'
      );
      CREATE TRIGGER IF NOT EXISTS kb_chunks_ai AFTER INSERT ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
      END;
      CREATE TRIGGER IF NOT EXISTS kb_chunks_ad AFTER DELETE ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
      END;
      CREATE TRIGGER IF NOT EXISTS kb_chunks_au AFTER UPDATE OF content ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
        INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
      END;
  `, fallbackSql: `
      CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
        content, content='kb_chunks', content_rowid='rowid', tokenize='unicode61'
      );
      CREATE TRIGGER IF NOT EXISTS kb_chunks_ai AFTER INSERT ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
      END;
      CREATE TRIGGER IF NOT EXISTS kb_chunks_ad AFTER DELETE ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, content) VALUES ('delete', old.rowid);
      END;
      CREATE TRIGGER IF NOT EXISTS kb_chunks_au AFTER UPDATE OF content ON kb_chunks BEGIN
        INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, content) VALUES ('delete', old.rowid);
        INSERT INTO kb_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
      END;
  ` },
  { id: "0010_case_event", sql: `
      -- 【步骤4·#4 案件时间线】CaseEvent（RE-4-案件时间线.md 实现规格 §3 数据模型落码）。
      -- ⚠ 过渡态：本表挂桥内轻量案件表族（matter_id FK → case_board_cases），MatterStore 解挂后
      -- 随案件族一起翻牌真源、届时随迁（决策台账 2026-10-27 03:35 同 0005_case_board 注）。
      -- 字段口径：日期/到期日一律 YYYY-MM-DD 字符串（后端强校验）；payload.amount_text 金额原文串
      -- （禁浮点，金额推理走 JC 桥）；status 六档默认 confirmed；origin 三通道
      -- （llm_extract=LLM 抽取 / auto=业务动作自动 / user=用户手工）；软删 deleted 位不物理删行；
      -- orig_json=编辑流被覆盖字段原值快照（D3 ↺ 恢复到抽取原值的落点）；索引 (matter_id, date)
      -- 同供 feed 倒序 50 与 full 区间扫描两口径（对拍 51）。
      CREATE TABLE IF NOT EXISTS case_events (
        event_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        event_type TEXT NOT NULL DEFAULT '',
        date TEXT,
        date_label TEXT,
        note TEXT,
        expires_at TEXT,
        status TEXT NOT NULL DEFAULT 'confirmed',
        importance TEXT NOT NULL DEFAULT 'normal',
        phase TEXT,
        side TEXT,
        origin TEXT NOT NULL DEFAULT 'llm_extract',
        source_refs_json TEXT NOT NULL DEFAULT '[]',
        payload_json TEXT,
        provenance TEXT NOT NULL DEFAULT 'ai',
        locked_fields_json TEXT NOT NULL DEFAULT '[]',
        orig_json TEXT,
        deleted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (matter_id) REFERENCES case_board_cases(id) ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS idx_case_events_matter_date ON case_events (matter_id, date);
  ` },
  { id: "0011_research_records", sql: `
      -- 【步骤4·#16 调研报告】ResearchRecord（RE-16-调研报告.md 实现规格 §3 数据模型落码）。
      -- 一条调研=一次课题：记录本体为 record_json 文档列（字段同构：id/query/timestamp/updatedAt/
      -- status/planning/reasoning/steps/updates/summary/editedSummary/reportRevision/blocks/
      -- threadId/turnId/error），键面列（status/query/thread_id/updated_at）供列表排序与
      -- 终态快速过滤；坏 JSON 容错回空（normalizeRecord 兜底）。
      CREATE TABLE IF NOT EXISTS research_records (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'running',
        query TEXT NOT NULL DEFAULT '',
        thread_id TEXT,
        record_json TEXT NOT NULL DEFAULT '{}',
        updated_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_research_records_updated ON research_records (updated_at);
  ` },
  { id: "0012_team_sync", sql: `
      -- 【步骤4·#26 LAN 团队同步】团队同步三表（RE-26-LAN 团队同步.md §3 数据模型落码）。
      -- 身份与密钥不进库：team_id/team_secret/pairing_code 等存配置文件 team 段（F13 等量），
      -- 库里只有快照/名单签名件/编辑记录；退团/解散/被踢三表全清（F15，防旧团队内容接力外带）。
      CREATE TABLE IF NOT EXISTS team_snapshots (
        member_id TEXT PRIMARY KEY,
        name TEXT NOT NULL DEFAULT '',
        seq INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT 'null'
      );
      CREATE TABLE IF NOT EXISTS team_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS team_edits (
        id TEXT PRIMARY KEY,
        team_id TEXT NOT NULL,
        editor_id TEXT NOT NULL,
        editor_name TEXT NOT NULL DEFAULT '',
        target_member_id TEXT NOT NULL,
        case_id TEXT NOT NULL DEFAULT '',
        case_name TEXT NOT NULL DEFAULT '',
        field TEXT NOT NULL,
        value TEXT NOT NULL,
        prev_value TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        applied_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_team_edits_target_status ON team_edits (target_member_id, status);
      CREATE INDEX IF NOT EXISTS idx_team_edits_created ON team_edits (created_at);
  ` },
  { id: "0013_conflict_check", sql: `
      -- 【步骤4·#5 冲突查重】冲突检索五表（RE-5-冲突查重.md 实现规格 §3.1 落码；命名随桥内既有表风格）。
      -- ⚠ 过渡态：候选主体挂桥内轻量案件表族 case_board_cases（决策台账 2026-10-27 03:35 同 0005 注：
      -- MatterStore 解挂后翻牌真源、随迁）。收案（intake）实体未接入前 subject_type='intake' 行恒空，
      -- 该检索面（在办收案命中/收案正式检索/转案闸）随 #2 收案模块接线。
      -- conflict_check=每次检索一行（预检/案件复核共用；subject_type='precheck' 恒 PENDING 不可下结论，
      -- 'matter' 为案件复核检索）；conflict_hit 逐条命中随 CASCADE 清。
      CREATE TABLE IF NOT EXISTS matter_parties (
        id TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL CHECK (subject_type IN ('matter','intake')),
        subject_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('CLIENT','OPPOSING_PARTY','THIRD_PARTY','CO_LITIGANT','AGENT','WITNESS','OTHER')),
        standing TEXT,
        name TEXT NOT NULL,
        id_number TEXT,
        social_code TEXT,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_matter_parties_name ON matter_parties (name);
      CREATE INDEX IF NOT EXISTS idx_matter_parties_id_number ON matter_parties (id_number);
      CREATE INDEX IF NOT EXISTS idx_matter_parties_social_code ON matter_parties (social_code);
      CREATE INDEX IF NOT EXISTS idx_matter_parties_subject ON matter_parties (subject_type, subject_id);
      CREATE TABLE IF NOT EXISTS conflict_clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        id_number TEXT,
        id_blind TEXT,
        deleted_at TEXT,
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_conflict_clients_name ON conflict_clients (name);
      CREATE INDEX IF NOT EXISTS idx_conflict_clients_blind ON conflict_clients (id_blind);
      CREATE TABLE IF NOT EXISTS conflict_client_matters (
        client_id TEXT NOT NULL,
        matter_id TEXT NOT NULL,
        PRIMARY KEY (client_id, matter_id)
      );
      CREATE TABLE IF NOT EXISTS conflict_check (
        id TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL CHECK (subject_type IN ('intake','matter','precheck')),
        subject_id TEXT,
        query_payload_json TEXT NOT NULL,
        subject_fingerprint TEXT,
        conclusion TEXT NOT NULL DEFAULT 'PENDING' CHECK (conclusion IN ('PENDING','SAME_SUBJECT','DIFFERENT','NEED_INFO')),
        decided_by TEXT,
        decided_at TEXT,
        note TEXT,
        checked_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_conflict_check_subject ON conflict_check (subject_type, subject_id, checked_at DESC);
      CREATE TABLE IF NOT EXISTS conflict_hit (
        id TEXT PRIMARY KEY,
        check_id TEXT NOT NULL,
        hit_type TEXT NOT NULL CHECK (hit_type IN ('HISTORICAL_PARTY','IN_PROGRESS_INTAKE')),
        target_type TEXT NOT NULL,
        target_id TEXT,
        matched_name TEXT NOT NULL,
        matched_field TEXT NOT NULL CHECK (matched_field IN ('name','idNumber')),
        matched_value TEXT NOT NULL,
        matched_ratio REAL NOT NULL DEFAULT 1,
        match_level TEXT,
        severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','BLOCKING')),
        reason TEXT,
        stored_role TEXT,
        stored_standing TEXT,
        FOREIGN KEY (check_id) REFERENCES conflict_check(id) ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS idx_conflict_hit_check ON conflict_hit (check_id);
  ` },
  // 桥内通用异步任务壳（机制规格-02，施工单-06）：QUEUED/RUNNING + 四终态；EXPIRED 读取时惰性翻转
  { id: "0014_async_tasks", sql: `
      CREATE TABLE IF NOT EXISTS async_tasks (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        ref TEXT,
        status TEXT NOT NULL DEFAULT 'QUEUED'
          CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
        payload_json TEXT NOT NULL DEFAULT '{}',
        result_ref TEXT,
        file_name TEXT,
        error_code TEXT,
        error_message TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        artifact_ttl INTEGER,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_async_tasks_created ON async_tasks (created_at DESC);
  ` },
  // 审批关卡 gate 节点（机制规格-01，施工单-06）：lock_version 乐观锁 + 事件流=审批记录=时间线
  { id: "0015_flow_gate", sql: `
      CREATE TABLE IF NOT EXISTS flow_nodes (
        id TEXT PRIMARY KEY,
        instance_code TEXT NOT NULL,
        node_code TEXT NOT NULL,
        node_type TEXT NOT NULL DEFAULT 'gate',
        status TEXT NOT NULL DEFAULT 'PENDING'
          CHECK (status IN ('PENDING','APPROVED','REJECTED','SUPERSEDED','SKIPPED')),
        assignee_user TEXT,
        lock_version INTEGER NOT NULL DEFAULT 1,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_flow_nodes_instance ON flow_nodes (instance_code, status);
      CREATE TABLE IF NOT EXISTS flow_node_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('created','process','transfer','force_transfer')),
        action TEXT,
        actor_user TEXT NOT NULL,
        target_user TEXT,
        reason TEXT,
        from_version INTEGER NOT NULL,
        to_version INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (node_id) REFERENCES flow_nodes(id) ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS idx_flow_node_events_node ON flow_node_events (node_id, id);
  ` },
  // 功能 #13 法条手册（RE-13 §3.2）：收藏两级（整法 FavLaw/行级 FavContent）+收藏夹+搜索历史，
  // 复用桥内轻量表惯例（对拍 12：收藏无幂等——重复收藏同夹=重复条目，应用层不查重；C4：同词重复
  // 提交=刷新原记录时间戳不新增，由桥面先查后写承接；C5：scope=shared 全局 / standalone 按 law_id 分域）。
  { id: "0016_lawbook", sql: `
      CREATE TABLE IF NOT EXISTS lawbook_fav_folders (
        workspace_key TEXT NOT NULL,
        folder_id TEXT NOT NULL,
        name TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (workspace_key, folder_id)
      );
      CREATE TABLE IF NOT EXISTS lawbook_fav_laws (
        workspace_key TEXT NOT NULL,
        row_id TEXT PRIMARY KEY,
        law_id TEXT NOT NULL,
        created_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_lawbook_fav_laws_law ON lawbook_fav_laws (workspace_key, law_id);
      CREATE TABLE IF NOT EXISTS lawbook_fav_contents (
        workspace_key TEXT NOT NULL,
        row_id TEXT PRIMARY KEY,
        law_id TEXT NOT NULL,
        line INTEGER NOT NULL DEFAULT 0,
        folder_id TEXT NOT NULL,
        created_at INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_lawbook_fav_contents_folder
        ON lawbook_fav_contents (workspace_key, folder_id);
      CREATE TABLE IF NOT EXISTS lawbook_search_history (
        workspace_key TEXT NOT NULL,
        row_id TEXT PRIMARY KEY,
        scope TEXT NOT NULL DEFAULT 'shared',
        law_id TEXT,
        text TEXT NOT NULL,
        search_t INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_lawbook_history_scope
        ON lawbook_search_history (workspace_key, scope, search_t DESC);
  ` },
  // 功能 #6 材料上传解析（RE-6 §3 数据模型落码；DDL 单源在 material_service.mjs）：
  // case_materials=MaterialRecord（同名版本链 supersedes/整型分 byte_size/状态三态 parsing|ready|failed）；
  // case_material_chunks(+FTS5)=语义分块检索面（对拍 33 FTS5，与 0003/0009 同款外部内容模式——
  // 过滤走 JOIN 后普通表列）；bridge_attachments(+scopes)=对话附件库（内容寻址 att_*、
  // thread/case 作用域授权，无作用域拒读 fail-closed）；material_parse_cache=五元组解析缓存（对拍 60）。
  // ⚠ 过渡态：case_id 现挂桥内轻量案件表族（同 0005/0010/0013 注：MatterStore 解挂后翻牌真源随迁）。
  { id: "0017_materials", sql: MATERIALS_DDL + MATERIALS_DDL_FTS_TRIGRAM, fallbackSql: MATERIALS_DDL + MATERIALS_DDL_FTS_FALLBACK },
  // 功能 #14 引证核验落账（RE-14 §3.2/§3.3 F4）：citation_checks 只追加（不更新不删除），
  // 消费路径闭合=GET /api/verify/citation/history（§3.3）+UI 历史抽屉（G10）。
  // 全局账（非 workspace 域）：核验记录本身零出域，落账面按规格七列钉死不扩。
  { id: "0018_citation_checks", sql: `
      CREATE TABLE IF NOT EXISTS citation_checks (
        id TEXT PRIMARY KEY,
        requested_at INTEGER NOT NULL,
        as_of TEXT NOT NULL,
        citation_text TEXT NOT NULL,
        status TEXT NOT NULL,
        code TEXT,
        verified_scoped INTEGER NOT NULL DEFAULT 0,
        reasons_json TEXT NOT NULL DEFAULT '[]'
      );
      CREATE INDEX IF NOT EXISTS idx_citation_checks_time
        ON citation_checks (requested_at DESC);
  ` },
  // 功能 #6 对话文件面板（RE-6 §3 UI：用户文件/Agent 产出 分组）——附件产出方标记列。
  // DDL 单源在 material_service.mjs（BRIDGE_ATTACHMENTS_PRODUCER_DDL）；0017 新库建表后由本迁移
  // 统一补列，存量库同句生效，两路径落同形状。缺省 'user' 不改变既有行行为。
  { id: "0019_attachment_producer", sql: BRIDGE_ATTACHMENTS_PRODUCER_DDL },
  // 功能 #42 电子数据取证（RE-42 §3.1 八实体落库）：源（哈希/解析/OCR 三态底座 A4）+ 块锚（页/坐标 E1）
  // + 行面（B2/B4 三件套寻址）+ 聊天段（H1）+ 虚拟归类（C1-C3）+ 候选清单（D1/D3）
  // + 审查标注（F3/F5/F11）+ 坐标批注（E3）+ 精化留痕（G2）。DDL 单源在 edisc_service.mjs。
  { id: "0020_edisc", sql: EDISC_DDL },
  // 【#21 安全层】工具决策审计专表（RE-21 增补 §3.3；DDL 单源在
  // tool_audit_service.mjs——迁移与合成自测共用同一份）。不并入 audit_log
  // 主链、不强加 HMAC（竞品无完整性链，不为其外加承诺）。deny 也入账；
  // args_summary 凭证键值替换不截断（红线见服务文件头注）。
  { id: "0021_tool_audits", sql: TOOL_AUDITS_DDL },
  // 功能 #35 Flow 工作流消费侧（RE-35 §3.4/§3.7）：流程定义（草稿/发布/内置三态+布局分离）+运行
  // （WAITING 持久化）+只追加事件流（HMAC attestation 链）+map 逐项 checkpoint+声明式能力注册面
  // +AI-run 一等记录+产物链（payloadDigest+citeReceipt）。DDL 单源在 flow_engine_service.mjs。
  { id: "0022_flow_engine", sql: FLOW_ENGINE_DDL },
  // 功能 #42 对拍收尾五表（RE-42 §2.F/§2.G；施工波三轮 20261031）：待证事实（F1）+
  // 候选形式六要素（F2）+三性评估（F4）+四类缺口（F6）+长任务生命周期（G5）。
  // DDL 单源在 edisc_service.mjs（EDISC_REVIEW_DDL）；0020 已应用库不重放，故独立迁移号。
  { id: "0023_edisc_review", sql: EDISC_REVIEW_DDL },
  // 功能 #32 整理与尽调（RE-32 §3）：看板/成果版本/字段模板/台账/清单/沿革六表；DDL 单源在 diligence_service.mjs。
  { id: "0024_diligence", sql: DILIGENCE_DDL },
];

export function openBridgeStore(port) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`bridge_store: 非法端口 ${port}`);
  const dir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
  mkdirSync(dir, { recursive: true });
  const dbPath = join(dir, `bridge-${port}.db`);
  // 功能 #29（RE-29 A1/A2）：库文件打开前是否存在 = 首启（pending）/旧库升级（completed/skipped）的判定事实源
  const existedBeforeOpen = existsSync(dbPath);
  const db = new DatabaseSync(dbPath);
  db.exec("PRAGMA busy_timeout = 5000");
  db.exec("PRAGMA foreign_keys = ON");
  db.exec("PRAGMA journal_mode = WAL");
  db.exec("PRAGMA synchronous = NORMAL");
  // 迁移账本：已应用的迁移不重放（对齐 RE-B1 §3.1 / 真产品 B4）
  db.exec("CREATE TABLE IF NOT EXISTS schema_migration(id TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)");
  const applied = new Set(db.prepare("SELECT id FROM schema_migration").all().map((r) => r.id));
  for (const m of MIGRATIONS) {
    if (applied.has(m.id)) continue;
    db.exec("BEGIN IMMEDIATE");
    try {
      try {
        db.exec(m.sql);
      } catch (first) {
        if (!m.fallbackSql) throw first;
        db.exec("ROLLBACK");
        db.exec("BEGIN IMMEDIATE");
        db.exec(m.fallbackSql); // RE-20 §3：trigram 不可用降级 unicode61（降级也失败才抛）
      }
      db.prepare("INSERT INTO schema_migration(id, applied_at) VALUES(?, ?)").run(m.id, Date.now());
      db.exec("COMMIT");
    } catch (e) {
      try { db.exec("ROLLBACK"); } catch { /* 已回滚/未开事务 */ }
      throw new Error(`bridge_store 迁移失败 ${m.id}: ${e?.message ?? e}`);
    }
  }
  const qSession = db.prepare(`
    INSERT INTO sessions (workspace_key, session_id, oc28_id, title, project_id, workspace_path,
      last_outcome, phase, seq, row_seq, busy, last_command_id, meta_json, created_at, updated_at, deleted)
    VALUES (@workspace_key, @session_id, @oc28_id, @title, @project_id, @workspace_path,
      @last_outcome, @phase, @seq, @row_seq, @busy, @last_command_id, @meta_json, @created_at, @updated_at, 0)
    ON CONFLICT(workspace_key, session_id) DO UPDATE SET
      oc28_id=@oc28_id, title=@title, project_id=@project_id, workspace_path=@workspace_path,
      last_outcome=@last_outcome, phase=@phase, seq=@seq, row_seq=@row_seq, busy=@busy,
      last_command_id=@last_command_id, meta_json=@meta_json, updated_at=@updated_at, deleted=0`);
  const qRow = db.prepare(`
    INSERT INTO session_rows (workspace_key, session_id, row_seq, kind, state, text, source_command_id, row_json)
    VALUES (@workspace_key, @session_id, @row_seq, @kind, @state, @text, @source_command_id, @row_json)
    ON CONFLICT(workspace_key, session_id, row_seq) DO UPDATE SET
      kind=@kind, state=@state, text=@text, source_command_id=@source_command_id, row_json=@row_json`);
  const qReceipt = db.prepare(`
    INSERT INTO command_receipts (workspace_key, command_id, session_id, ack_json, outcome, created_at)
    VALUES (@workspace_key, @command_id, @session_id, @ack_json, @outcome, @created_at)
    ON CONFLICT(workspace_key, command_id) DO UPDATE SET
      session_id=@session_id, ack_json=@ack_json, outcome=@outcome`);
  // 白名单列动态 UPDATE：列名只出自本文件集合，值全走命名参数——不拼任何外部串。
  // pkCol=主键列名（case_board_* 用 id；case_events 用 event_id）。
  const updateWhitelisted = (table, allowed, id, cols, pkCol = "id") => {
    const keys = Object.keys(cols).filter((k) => allowed.has(k));
    if (!keys.length) return;
    db.prepare(`UPDATE ${table} SET ${keys.map((k) => k + " = @" + k).join(", ")} WHERE ${pkCol} = @id`)
      .run({ ...cols, id });
  };
  const CASE_COLS = new Set(["name", "cause", "case_no", "court", "court_type", "claim_amount_cents",
    "plaintiffs_json", "defendants_json", "judges_json", "workflow_status", "workflow_locked",
    "overrides_json", "sort_order", "updated_at"]);
  const TODO_COLS = new Set(["title", "done", "done_at", "due_date", "updated_at"]);
  const EVENT_COLS = new Set(["date", "title", "note", "case_id", "kind", "location", "start_at", "end_at",
    "trip", "remind", "remind_minutes"]);
  const CE_COLS = new Set(["event_type", "date", "date_label", "note", "expires_at", "status", "importance",
    "phase", "side", "origin", "source_refs_json", "payload_json", "provenance", "locked_fields_json",
    "orig_json", "deleted", "updated_at"]);
  return {
    dbPath,
    db,
    existedBeforeOpen, // 功能 #29：initOnboardingState 的首启/升级判定入参
    upsertSession: (rec) => qSession.run(rec),
    upsertRow: (rec) => qRow.run(rec),
    putReceipt: (rec) => qReceipt.run(rec),
    listSessions: () => db.prepare("SELECT * FROM sessions WHERE deleted = 0 ORDER BY created_at").all(),
    listRows: (workspaceKey, sessionId) => db.prepare(
      "SELECT * FROM session_rows WHERE workspace_key = ? AND session_id = ? ORDER BY row_seq").all(workspaceKey, sessionId),
    listReceipts: () => db.prepare("SELECT * FROM command_receipts").all(),
    // ── 功能 #15 案内文档搜索（RE-15 v2：普通表权威副本 + 触发器同步 external-content FTS5）──
    upsertDocumentChunk: (rec) => {
      db.prepare(`
        INSERT INTO document_chunks (workspace_key, session_id, chunk_id, source_label, kind, created_at, text)
        VALUES (@workspace_key, @session_id, @chunk_id, @source_label, @kind, @created_at, @text)
        ON CONFLICT(workspace_key, session_id, chunk_id) DO UPDATE SET
          source_label=@source_label, kind=@kind, created_at=@created_at, text=@text`).run(rec);
    },
    searchDocumentChunks: (workspaceKey, sessionId, query, limit) => {
      // trigram MATCH 要求 ≥3 字符；短词/零命中回落普通表 LIKE 子串（单案量级小可接受）。
      // 会话/工作区过滤一律走 JOIN 后的普通表列——FTS5 虚表直滤 UNINDEXED/外部内容列不可靠（0003 注）。
      const ranked = (() => {
        try {
          return db.prepare(`
            SELECT c.chunk_id AS chunk_id, c.source_label AS source_label, c.kind AS kind,
                   c.created_at AS created_at, c.text AS text, bm25(document_chunks_fts) AS rank
            FROM document_chunks_fts f
            JOIN document_chunks c ON c.rowid = f.rowid
            WHERE document_chunks_fts MATCH ? AND c.workspace_key = ? AND c.session_id = ?
            ORDER BY rank LIMIT ?`).all(`"${query.replace(/"/g, '""')}"`, workspaceKey, sessionId, limit);
        } catch { return []; }
      })();
      if (ranked.length > 0) return { hits: ranked, mode: "fts" };
      const likes = db.prepare(`
        SELECT chunk_id, source_label, kind, created_at, text
        FROM document_chunks
        WHERE workspace_key = ? AND session_id = ? AND text LIKE ? ESCAPE '\\'
        ORDER BY created_at DESC LIMIT ?`).all(workspaceKey, sessionId, `%${query.replace(/[\\%_]/g, "\\$&")}%`, limit);
      return { hits: likes, mode: "like" };
    },
    // ── 功能 #23 对话分支画布：editUserQuery rewind 的裁剪出库 ──
    // row.removed 只裁进程内投影；session_rows 里被裁行必须真删，否则桥重启恢复复活旧分支。
    // 连带清 #15 全文索引块（chunk_id=rowId 字符串），被裁轮次不再可搜。
    deleteRowsFrom: (workspaceKey, sessionId, fromRowId) => {
      db.prepare("DELETE FROM session_rows WHERE workspace_key = ? AND session_id = ? AND row_seq >= ?")
        .run(workspaceKey, sessionId, fromRowId);
      db.prepare("DELETE FROM document_chunks WHERE workspace_key = ? AND session_id = ? AND CAST(chunk_id AS INTEGER) >= ?")
        .run(workspaceKey, sessionId, fromRowId);
    },
    // ── 功能 #11 红线改稿：记录/修订项 CRUD（decision 与终态整体行更新）──
    upsertRedline: (rec) => {
      db.prepare(`
        INSERT INTO redline_revisions (workspace_key, revision_id, material_name, instruction, status,
          original_text, revised_text, final_text, final_path, error, created_at, updated_at)
        VALUES (@workspace_key, @revision_id, @material_name, @instruction, @status,
          @original_text, @revised_text, @final_text, @final_path, @error, @created_at, @updated_at)
        ON CONFLICT(workspace_key, revision_id) DO UPDATE SET
          material_name=@material_name, instruction=@instruction, status=@status,
          original_text=@original_text, revised_text=@revised_text, final_text=@final_text,
          final_path=@final_path, error=@error, updated_at=@updated_at`).run(rec);
    },
    getRedline: (workspaceKey, revisionId) =>
      db.prepare("SELECT * FROM redline_revisions WHERE workspace_key = ? AND revision_id = ?").get(workspaceKey, revisionId) ?? null,
    listRedlines: (workspaceKey) =>
      db.prepare("SELECT * FROM redline_revisions WHERE workspace_key = ? ORDER BY created_at DESC").all(workspaceKey),
    putRedlineItems: (workspaceKey, revisionId, items) => {
      const q = db.prepare(`
        INSERT INTO redline_items (workspace_key, revision_id, item_idx, type, a_start, a_count, b_start, b_count, old_text, new_text, decision)
        VALUES (@workspace_key, @revision_id, @item_idx, @type, @a_start, @a_count, @b_start, @b_count, @old_text, @new_text, @decision)
        ON CONFLICT(workspace_key, revision_id, item_idx) DO UPDATE SET
          type=@type, a_start=@a_start, a_count=@a_count, b_start=@b_start, b_count=@b_count,
          old_text=@old_text, new_text=@new_text, decision=@decision`);
      const rows = items.map((it) => ({ workspace_key: workspaceKey, revision_id: revisionId, ...it }));
      db.exec("BEGIN IMMEDIATE");
      try { for (const r of rows) q.run(r); db.exec("COMMIT"); }
      catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    listRedlineItems: (workspaceKey, revisionId) =>
      db.prepare("SELECT * FROM redline_items WHERE workspace_key = ? AND revision_id = ? ORDER BY item_idx").all(workspaceKey, revisionId),
    setRedlineItemDecision: (workspaceKey, revisionId, itemIdx, decision) => {
      db.prepare("UPDATE redline_items SET decision = ? WHERE workspace_key = ? AND revision_id = ? AND item_idx = ?")
        .run(decision, workspaceKey, revisionId, itemIdx);
    },
    // ── 【步骤4·案件族底座】MatterLite 轻量案件表 CRUD（RE-3 §3.2；过渡态标注见迁移 0005 注）──
    listCases: () => db.prepare("SELECT * FROM case_board_cases ORDER BY updated_at DESC, id").all(),
    getCase: (id) => db.prepare("SELECT * FROM case_board_cases WHERE id = ?").get(id) ?? null,
    insertCase: (rec) => db.prepare(`
      INSERT INTO case_board_cases (id, name, cause, case_no, court, court_type, claim_amount_cents,
        plaintiffs_json, defendants_json, judges_json, workflow_status, workflow_locked, overrides_json,
        sort_order, updated_at)
      VALUES (@id, @name, @cause, @case_no, @court, @court_type, @claim_amount_cents,
        @plaintiffs_json, @defendants_json, @judges_json, @workflow_status, @workflow_locked,
        @overrides_json, @sort_order, @updated_at)`).run(rec),
    updateCase: (id, cols) => updateWhitelisted("case_board_cases", CASE_COLS, id, cols),
    deleteCase: (id) => db.prepare("DELETE FROM case_board_cases WHERE id = ?").run(id),
    insertTodo: (rec) => db.prepare(`
      INSERT INTO case_board_todos (id, case_id, title, done, done_at, due_date, created_at, updated_at)
      VALUES (@id, @case_id, @title, @done, @done_at, @due_date, @created_at, @updated_at)`).run(rec),
    getTodo: (id) => db.prepare("SELECT * FROM case_board_todos WHERE id = ?").get(id) ?? null,
    listTodos: (caseId) => caseId
      ? db.prepare("SELECT * FROM case_board_todos WHERE case_id = ? ORDER BY created_at, id").all(caseId)
      : db.prepare("SELECT * FROM case_board_todos ORDER BY created_at, id").all(),
    updateTodo: (id, cols) => updateWhitelisted("case_board_todos", TODO_COLS, id, cols),
    deleteTodo: (id) => db.prepare("DELETE FROM case_board_todos WHERE id = ?").run(id),
    insertEvent: (rec) => db.prepare(`
      INSERT INTO case_board_events (id, date, title, note, case_id, kind, location, start_at, end_at,
        trip, remind, remind_minutes, created_at)
      VALUES (@id, @date, @title, @note, @case_id, @kind, @location, @start_at, @end_at,
        @trip, @remind, @remind_minutes, @created_at)`).run(rec),
    getEvent: (id) => db.prepare("SELECT * FROM case_board_events WHERE id = ?").get(id) ?? null,
    // 排序：date 升序、同日有时刻者按 start_at 先于 date-only 行、再按创建序（确定性）
    listEvents: () => db.prepare(`SELECT * FROM case_board_events
      ORDER BY date, CASE WHEN start_at IS NULL THEN 1 ELSE 0 END, start_at, created_at, id`).all(),
    updateEvent: (id, cols) => updateWhitelisted("case_board_events", EVENT_COLS, id, cols),
    deleteEvent: (id) => db.prepare("DELETE FROM case_board_events WHERE id = ?").run(id),
    // 案件删除时解绑日程的 case_id（0007 增列无 FK，桥面显式清；待办走 0005 FK 级联）
    clearEventCaseLink: (caseId) =>
      db.prepare("UPDATE case_board_events SET case_id = NULL WHERE case_id = ?").run(caseId),
    // ── agent 可读日程/任务面（对拍行 86；LX mcp-schedule list_schedule/list_tasks 只读查询等量）──
    // 过滤片段全部为固定串、值走命名参数——不拼任何外部串；limit 由桥面钳到 1..50 后传入。
    listEventsQuery: (f) => {
      const where = [];
      const p = {};
      if (f.from) { where.push("date >= @from"); p.from = f.from; }
      if (f.to) { where.push("date <= @to"); p.to = f.to; }
      if (f.caseId) { where.push("case_id = @caseId"); p.caseId = f.caseId; }
      p.limit = f.limit;
      return db.prepare(`SELECT * FROM case_board_events ${where.length ? "WHERE " + where.join(" AND ") : ""}
        ORDER BY date, CASE WHEN start_at IS NULL THEN 1 ELSE 0 END, start_at, created_at, id
        LIMIT @limit`).all(p);
    },
    // LX list_tasks 口径 ORDER BY done ASC, due ASC, rowid DESC；due_date NULL 沉底（无期限不占前位）
    listTasksQuery: (f) => {
      const where = [];
      const p = {};
      if (f.caseId) { where.push("case_id = @caseId"); p.caseId = f.caseId; }
      if (f.done !== undefined && f.done !== null) { where.push("done = @done"); p.done = f.done ? 1 : 0; }
      p.limit = f.limit;
      return db.prepare(`SELECT * FROM case_board_todos ${where.length ? "WHERE " + where.join(" AND ") : ""}
        ORDER BY done ASC, CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date ASC, rowid DESC
        LIMIT @limit`).all(p);
    },
    // ── 【步骤4·#4 案件时间线】CaseEvent CRUD（RE-4 §3；⚠过渡态随案件族翻牌，迁移 0010 注）──
    // 同事务助手（LL F2 等量：业务写与时间线写同事务提交——任一失败整体回滚）
    withTransaction: (fn) => {
      db.exec("BEGIN IMMEDIATE");
      try { const r = fn(); db.exec("COMMIT"); return r; }
      catch (e) { try { db.exec("ROLLBACK"); } catch { /* 未开事务/已回滚 */ } throw e; }
    },
    insertCaseEvent: (rec) => db.prepare(`
      INSERT INTO case_events (event_id, matter_id, event_type, date, date_label, note, expires_at,
        status, importance, phase, side, origin, source_refs_json, payload_json, provenance,
        locked_fields_json, orig_json, deleted, created_at, updated_at)
      VALUES (@event_id, @matter_id, @event_type, @date, @date_label, @note, @expires_at,
        @status, @importance, @phase, @side, @origin, @source_refs_json, @payload_json, @provenance,
        @locked_fields_json, @orig_json, @deleted, @created_at, @updated_at)`).run(rec),
    getCaseEvent: (eventId) => db.prepare("SELECT * FROM case_events WHERE event_id = ?").get(eventId) ?? null,
    // full 口径原始行（deleted=0 固定过滤；C3 排序在桥面纯函数 sortCaseEventsFull）
    listCaseEventsByMatter: (matterId) =>
      db.prepare("SELECT * FROM case_events WHERE matter_id = ? AND deleted = 0").all(matterId),
    // feed 口径（LL F7 等量）：date DESC, created_at DESC LIMIT 50；factTypes=null=不过滤
    //（内部全量口径）；数组=FACT_EVENT_TYPES 常量白名单（客户侧可见性过滤在查询层执行——对拍 50）
    listCaseEventsFeed: (matterId, factTypes, limit) => {
      if (!factTypes) {
        return db.prepare(`SELECT * FROM case_events WHERE matter_id = ? AND deleted = 0
          ORDER BY date DESC, created_at DESC LIMIT ?`).all(matterId, limit);
      }
      const ph = factTypes.map(() => "?").join(",");
      return db.prepare(`SELECT * FROM case_events WHERE matter_id = ? AND deleted = 0
        AND event_type IN (${ph}) ORDER BY date DESC, created_at DESC LIMIT ?`).all(matterId, ...factTypes, limit);
    },
    listDeletedCaseEvents: (matterId) =>
      db.prepare("SELECT * FROM case_events WHERE matter_id = ? AND deleted = 1 ORDER BY date, created_at").all(matterId),
    // 看板联动源（下一节点/期限阶梯/月历并入）：跨案全量（deleted=0）
    listCaseEventsAll: () => db.prepare("SELECT * FROM case_events WHERE deleted = 0").all(),
    updateCaseEvent: (eventId, cols) => updateWhitelisted("case_events", CE_COLS, eventId, cols, "event_id"),
    // ── 【步骤4·#16 调研报告】ResearchRecord CRUD（RE-16 §3；文档列+键面列双形）──
    listResearchRecords: () => db.prepare("SELECT * FROM research_records ORDER BY updated_at DESC, id DESC").all(),
    getResearchRecord: (id) => db.prepare("SELECT * FROM research_records WHERE id = ?").get(id) ?? null,
    upsertResearchRecord: (rec) => db.prepare(`
      INSERT INTO research_records (id, status, query, thread_id, record_json, updated_at)
      VALUES (@id, @status, @query, @thread_id, @record_json, @updated_at)
      ON CONFLICT(id) DO UPDATE SET
        status=@status, query=@query, thread_id=@thread_id, record_json=@record_json, updated_at=@updated_at`)
      .run({ id: rec.id, status: rec.status, query: rec.query, thread_id: rec.thread_id ?? null,
        record_json: rec.record_json, updated_at: rec.updated_at }),
    deleteResearchRecord: (id) => db.prepare("DELETE FROM research_records WHERE id = ?").run(id),
    clearResearchRecords: () => db.prepare("DELETE FROM research_records").run(),
    // ── 功能 #19 轻量知识图谱（RE-19）：graph 文档式 JSON 一图一行 CRUD（乐观锁版本列在 revision）──
    getCaseGraph: (workspaceKey, caseId) =>
      db.prepare("SELECT * FROM case_graphs WHERE workspace_key = ? AND case_id = ?").get(workspaceKey, caseId) ?? null,
    upsertCaseGraph: (workspaceKey, caseId, graphJson, revision, updatedAt) =>
      db.prepare(`
        INSERT INTO case_graphs (workspace_key, case_id, graph_json, revision, updated_at)
        VALUES (@workspace_key, @case_id, @graph_json, @revision, @updated_at)
        ON CONFLICT(workspace_key, case_id) DO UPDATE SET
          graph_json=@graph_json, revision=@revision, updated_at=@updated_at`)
        .run({ workspace_key: workspaceKey, case_id: caseId, graph_json: graphJson, revision, updated_at: updatedAt }),
    deleteCaseGraph: (workspaceKey, caseId) =>
      db.prepare("DELETE FROM case_graphs WHERE workspace_key = ? AND case_id = ?").run(workspaceKey, caseId),
    // ── 功能 #20 所内知识问答（RE-20 §3）：文集/文档/块/FTS 召回/账本 ──
    // FTS 只做候选召回（bm25，≤240，B51）；打分排序由 kb_service 多因子与内存路径同源完成。
    kbFtsMode: () => {
      const row = db.prepare("SELECT sql FROM sqlite_master WHERE name='kb_chunks_fts'").get();
      return row && /tokenize\s*=\s*'trigram'/i.test(row.sql) ? "trigram" : row ? "unicode61" : "none";
    },
    kbCountDocuments: () => db.prepare("SELECT COUNT(*) AS n FROM kb_documents").get().n,
    kbListDocuments: () => db.prepare("SELECT * FROM kb_documents ORDER BY rel_path").all(),
    kbGetDocument: (relPath) => db.prepare("SELECT * FROM kb_documents WHERE rel_path = ?").get(relPath) ?? null,
    kbUpsertDocument: (rec) => db.prepare(`
      INSERT INTO kb_documents (id, collection_path, title, rel_path, ext, size_bytes, mtime_ms, content_hash,
        category, tags_json, keywords_json, indexed_at)
      VALUES (@id, @collection_path, @title, @rel_path, @ext, @size_bytes, @mtime_ms, @content_hash,
        @category, @tags_json, @keywords_json, @indexed_at)
      ON CONFLICT(rel_path) DO UPDATE SET
        collection_path=@collection_path, title=@title, ext=@ext, size_bytes=@size_bytes,
        mtime_ms=@mtime_ms, content_hash=@content_hash, category=@category,
        tags_json=@tags_json, keywords_json=@keywords_json, indexed_at=@indexed_at`).run(rec),
    kbDeleteDocument: (relPath) => db.prepare("DELETE FROM kb_documents WHERE rel_path = ?").run(relPath),
    kbUpdateDocumentPath: (oldRel, rel) => db.prepare(
      "UPDATE kb_documents SET rel_path = ?, collection_path = ?, title = ? WHERE rel_path = ?")
      .run(rel, rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "", titleOfRel(rel), oldRel),
    kbReplaceChunks: (docId, chunks) => {
      const del = db.prepare("DELETE FROM kb_chunks WHERE document_id = ?");
      const ins = db.prepare(`
        INSERT INTO kb_chunks (id, document_id, chunk_index, heading_path_json, article_number, content,
          char_start, char_end, chunk_hash, provenance_id)
        VALUES (@id, @document_id, @chunk_index, @heading_path_json, @article_number, @content,
          @char_start, @char_end, @chunk_hash, @provenance_id)`);
      db.exec("BEGIN IMMEDIATE");
      try {
        del.run(docId);
        chunks.forEach((c, i) => ins.run({
          id: docId + "_" + i, document_id: docId, chunk_index: i,
          heading_path_json: JSON.stringify(c.headingPath ?? []), article_number: c.articleNumber ?? null,
          content: c.content, char_start: c.charStart ?? 0, char_end: c.charEnd ?? 0,
          chunk_hash: c.chunkHash ?? "", provenance_id: docId,
        }));
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    kbRecallFts: (matchExpr, folderPrefix, limit) => {
      // MATCH 串由桥面拼（token OR 串、内部转义）；folderPrefix 过滤走 JOIN 后普通表列（0003 教训）
      const rows = db.prepare(`
        SELECT c.id AS chunk_id, c.document_id AS document_id, c.content AS content,
               c.article_number AS article_number,
               d.title AS title, d.rel_path AS rel_path, d.category AS category,
               d.keywords_json AS keywords_json, bm25(kb_chunks_fts) AS rank
        FROM kb_chunks_fts f
        JOIN kb_chunks c ON c.rowid = f.rowid
        JOIN kb_documents d ON d.id = c.document_id
        WHERE kb_chunks_fts MATCH ? ${folderPrefix ? "AND d.rel_path LIKE ?" : ""}
        ORDER BY rank LIMIT ?`).all(...(folderPrefix ? [matchExpr, folderPrefix + "/%", limit] : [matchExpr, limit]));
      return rows;
    },
    kbScanChunks: (folderPrefix, limit) => db.prepare(`
      SELECT c.id AS chunk_id, c.document_id AS document_id, c.content AS content,
             c.article_number AS article_number,
             d.title AS title, d.rel_path AS rel_path, d.category AS category,
             d.keywords_json AS keywords_json
      FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id
      ${folderPrefix ? "WHERE d.rel_path LIKE ?" : ""}
      LIMIT ?`).all(...(folderPrefix ? [folderPrefix + "/%", limit] : [limit])),
    kbGetMeta: (key) => db.prepare("SELECT value FROM kb_meta WHERE key = ?").get(key)?.value ?? null,
    kbSetMeta: (key, value) => db.prepare(`
      INSERT INTO kb_meta (key, value) VALUES (?, ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value`).run(key, String(value)),
    kbListCollections: () => db.prepare("SELECT * FROM kb_collections ORDER BY path").all(),
    kbUpsertCollection: (rec) => db.prepare(`
      INSERT INTO kb_collections (id, name, path, created_at, updated_at)
      VALUES (@id, @name, @path, @created_at, @updated_at)
      ON CONFLICT(path) DO UPDATE SET name=@name, updated_at=@updated_at`).run(rec),
    kbDeleteCollection: (path) => db.prepare("DELETE FROM kb_collections WHERE path = ?").run(path),
    kbDeleteCollectionsUnder: (path) => db.prepare(
      "DELETE FROM kb_collections WHERE path = ? OR path LIKE ?").run(path, path + "/%"),
    kbUpdateCollectionPath: (oldPath, newPath) => db.prepare(
      "UPDATE kb_collections SET path = ?, updated_at = ? WHERE path = ?").run(newPath, Date.now(), oldPath),
    // ── 【步骤4·#26 LAN 团队同步】团队三表存取（RE-26 §3 数据模型；身份/密钥不进库，F13）──
    teamGetSnapshot: (memberId) =>
      db.prepare("SELECT * FROM team_snapshots WHERE member_id = ?").get(memberId) ?? null,
    teamAllSnapshots: () => db.prepare("SELECT * FROM team_snapshots ORDER BY member_id").all(),
    teamPutSnapshot: (r) => db.prepare(`
      INSERT INTO team_snapshots (member_id, name, seq, updated_at, payload_json)
      VALUES (@member_id, @name, @seq, @updated_at, @payload_json)
      ON CONFLICT(member_id) DO UPDATE SET
        name=@name, seq=@seq, updated_at=@updated_at, payload_json=@payload_json`).run(
      { member_id: r.member_id, name: r.name, seq: r.seq, updated_at: r.updated_at, payload_json: r.payload_json }),
    teamGetState: (key) => db.prepare("SELECT value FROM team_state WHERE key = ?").get(key)?.value ?? null,
    teamSetState: (key, value) => db.prepare(`
      INSERT INTO team_state (key, value) VALUES (?, ?)
      ON CONFLICT(key) DO UPDATE SET value = excluded.value`).run(key, String(value)),
    teamGetEdit: (id) => db.prepare("SELECT * FROM team_edits WHERE id = ?").get(id) ?? null,
    teamPutEdit: (r) => db.prepare(`
      INSERT INTO team_edits (id, team_id, editor_id, editor_name, target_member_id, case_id, case_name,
        field, value, prev_value, status, created_at, applied_at)
      VALUES (@id, @team_id, @editor_id, @editor_name, @target_member_id, @case_id, @case_name,
        @field, @value, @prev_value, @status, @created_at, @applied_at)
      ON CONFLICT(id) DO UPDATE SET
        editor_name=@editor_name, field=@field, value=@value, prev_value=@prev_value,
        status=@status, applied_at=@applied_at`).run(r),
    // 合并入口白名单列更新（状态机只升不降的落点；appliedAt 仅 applied 时回填）
    teamUpdateEditStatus: (id, status, appliedAt) =>
      db.prepare("UPDATE team_edits SET status = ?, applied_at = COALESCE(?, applied_at) WHERE id = ?")
        .run(status, appliedAt, id),
    teamListEditsForExchange: (limit) =>
      db.prepare("SELECT * FROM team_edits ORDER BY created_at DESC, id DESC LIMIT ?").all(limit),
    teamListEditsByTarget: (targetMemberId, status) =>
      db.prepare("SELECT * FROM team_edits WHERE target_member_id = ? AND status = ? ORDER BY created_at")
        .all(targetMemberId, status),
    teamListEditsRelated: (memberIds, editorId, limit) => {
      if (!memberIds.length) return db.prepare("SELECT * FROM team_edits WHERE editor_id = ? ORDER BY created_at DESC, id DESC LIMIT ?").all(editorId, limit);
      const ph = memberIds.map(() => "?").join(",");
      return db.prepare(`SELECT * FROM team_edits WHERE (target_member_id IN (${ph}) OR editor_id = ?)` +
        " ORDER BY created_at DESC, id DESC LIMIT ?").all(...memberIds, editorId, limit);
    },
    // 退团/解散/被踢清三表（F15：漏清会把旧团队案件名/备注接力外带给新团队，竞品 0.3.12 修等量）
    teamClearAll: () => {
      db.prepare("DELETE FROM team_snapshots").run();
      db.prepare("DELETE FROM team_state").run();
      db.prepare("DELETE FROM team_edits").run();
    },
    // ── 【步骤4·#5 冲突查重】当事人/客户档案/检索记录存取（RE-5 §3.1；⚠过渡态随案件族翻牌，
    //    迁移 0013_conflict_check 注）——候选查询全部固定片段+绑定参数，probes 由桥面纯模型
    //    生成后逐个绑定（LIKE %probe%，NOCASE 折叠 ASCII；中文不受影响）。take 上限即竞品
    //    精确/模糊分查的窗口口径（C8）：历史/收案精确无上限、模糊 20、客户面 50，由桥面传入。──
    // 主体当事人：整体替换式写（先清后插，调用方裹事务）
    deletePartiesBySubject: (subjectType, subjectId) =>
      db.prepare("DELETE FROM matter_parties WHERE subject_type = ? AND subject_id = ?").run(subjectType, subjectId),
    insertParty: (rec) => db.prepare(`
      INSERT INTO matter_parties (id, subject_type, subject_id, role, standing, name, id_number, social_code, created_at)
      VALUES (@id, @subject_type, @subject_id, @role, @standing, @name, @id_number, @social_code, @created_at)`).run(rec),
    listPartiesBySubject: (subjectType, subjectId) =>
      db.prepare("SELECT * FROM matter_parties WHERE subject_type = ? AND subject_id = ? ORDER BY rowid")
        .all(subjectType, subjectId),
    // 候选面（①历史案件当事人=挂 matter 的 party；②在办收案当事人=挂 intake 的 party——
    // intake 实体未接入时恒空集，面随 #2 接线）。命中候选附案件最小披露列（brief_*，E4）。
    conflictPartyExactByName: (subjectType, name, excludeSubjectId) => {
      const brief = subjectType === "matter"
        ? ", c.case_no AS brief_case_no, c.name AS brief_name, c.cause AS brief_cause, c.court_type AS brief_court_type, c.workflow_status AS brief_status"
        : ", NULL AS brief_case_no, NULL AS brief_name, NULL AS brief_cause, NULL AS brief_court_type, NULL AS brief_status";
      const join = subjectType === "matter" ? "JOIN case_board_cases c ON c.id = p.subject_id" : "";
      const excl = excludeSubjectId ? " AND p.subject_id != ?" : "";
      return db.prepare(`SELECT p.*${brief} FROM matter_parties p ${join}
        WHERE p.subject_type = ? AND p.name = ?${excl}`).all(...(excludeSubjectId ? [subjectType, name, excludeSubjectId] : [subjectType, name]));
    },
    conflictPartyExactById: (subjectType, variants, excludeSubjectId) => {
      if (!variants.length) return [];
      const brief = subjectType === "matter"
        ? ", c.case_no AS brief_case_no, c.name AS brief_name, c.cause AS brief_cause, c.court_type AS brief_court_type, c.workflow_status AS brief_status"
        : ", NULL AS brief_case_no, NULL AS brief_name, NULL AS brief_cause, NULL AS brief_court_type, NULL AS brief_status";
      const join = subjectType === "matter" ? "JOIN case_board_cases c ON c.id = p.subject_id" : "";
      const ph = variants.map(() => "?").join(",");
      const excl = excludeSubjectId ? " AND p.subject_id != ?" : "";
      return db.prepare(`SELECT p.*${brief} FROM matter_parties p ${join}
        WHERE p.subject_type = ? AND (p.id_number IN (${ph}) OR p.social_code IN (${ph}))${excl}`)
        .all(...(excludeSubjectId
          ? [subjectType, ...variants, ...variants, excludeSubjectId]
          : [subjectType, ...variants, ...variants]));
    },
    conflictPartyFuzzyByProbes: (subjectType, probes, fuzzyLimit, excludeSubjectId) => {
      if (!probes.length) return [];
      const brief = subjectType === "matter"
        ? ", c.case_no AS brief_case_no, c.name AS brief_name, c.cause AS brief_cause, c.court_type AS brief_court_type, c.workflow_status AS brief_status"
        : ", NULL AS brief_case_no, NULL AS brief_name, NULL AS brief_cause, NULL AS brief_court_type, NULL AS brief_status";
      const join = subjectType === "matter" ? "JOIN case_board_cases c ON c.id = p.subject_id" : "";
      const ors = probes.map(() => "p.name LIKE ? COLLATE NOCASE").join(" OR ");
      const excl = excludeSubjectId ? " AND p.subject_id != ?" : "";
      const args = probes.map((pr) => `%${pr}%`);
      return db.prepare(`SELECT p.*${brief} FROM matter_parties p ${join}
        WHERE p.subject_type = ? AND (${ors})${excl} LIMIT ?`)
        .all(...(excludeSubjectId ? [subjectType, ...args, excludeSubjectId, fuzzyLimit] : [subjectType, ...args, fuzzyLimit]));
    },
    // ③客户档案候选（软删滤 deleted_at，C1）；孤立客户不产出命中——回溯在桥面按关联案件展开
    conflictClientExactByName: (name) =>
      db.prepare("SELECT * FROM conflict_clients WHERE name = ? AND deleted_at IS NULL").all(name),
    conflictClientFuzzyByProbes: (probes, limit) => {
      if (!probes.length) return [];
      const ors = probes.map(() => "name LIKE ? COLLATE NOCASE").join(" OR ");
      return db.prepare(`SELECT * FROM conflict_clients WHERE deleted_at IS NULL AND (${ors}) LIMIT ?`)
        .all(...probes.map((pr) => `%${pr}%`), limit);
    },
    conflictClientByBlind: (blind) =>
      blind ? db.prepare("SELECT * FROM conflict_clients WHERE id_blind = ? AND deleted_at IS NULL").all(blind) : [],
    conflictClientMatters: (clientId) =>
      db.prepare(`SELECT cm.matter_id, c.case_no AS brief_case_no, c.name AS brief_name, c.cause AS brief_cause,
        c.court_type AS brief_court_type, c.workflow_status AS brief_status
        FROM conflict_client_matters cm JOIN case_board_cases c ON c.id = cm.matter_id
        WHERE cm.client_id = ? ORDER BY cm.matter_id`).all(clientId),
    conflictUpsertClient: (rec) => db.prepare(`
      INSERT INTO conflict_clients (id, name, id_number, id_blind, deleted_at, created_at)
      VALUES (@id, @name, @id_number, @id_blind, @deleted_at, @created_at)
      ON CONFLICT(id) DO UPDATE SET
        name=@name, id_number=@id_number, id_blind=@id_blind, deleted_at=@deleted_at`).run(rec),
    conflictGetClient: (id) => db.prepare("SELECT * FROM conflict_clients WHERE id = ?").get(id) ?? null,
    conflictListClients: () => db.prepare("SELECT * FROM conflict_clients ORDER BY created_at, id").all(),
    conflictSetClientMatters: (clientId, matterIds) => {
      db.prepare("DELETE FROM conflict_client_matters WHERE client_id = ?").run(clientId);
      const ins = db.prepare("INSERT INTO conflict_client_matters (client_id, matter_id) VALUES (?, ?)");
      for (const m of matterIds) ins.run(clientId, m);
    },
    conflictInsertCheck: (rec) => db.prepare(`
      INSERT INTO conflict_check (id, subject_type, subject_id, query_payload_json, subject_fingerprint,
        conclusion, decided_by, decided_at, note, checked_at)
      VALUES (@id, @subject_type, @subject_id, @query_payload_json, @subject_fingerprint,
        @conclusion, @decided_by, @decided_at, @note, @checked_at)`).run(rec),
    conflictUpdateCheckConclusion: (id, cols) => db.prepare(`
      UPDATE conflict_check SET conclusion = @conclusion, decided_by = @decided_by,
        decided_at = @decided_at, note = @note WHERE id = @id`).run({ id, ...cols }),
    conflictGetCheck: (id) => db.prepare("SELECT * FROM conflict_check WHERE id = ?").get(id) ?? null,
    // subjectType=null=全局列表（不筛主体类型）；subjectId=null 配 precheck=检索所有预检行
    conflictListChecksBySubject: (subjectType, subjectId) => {
      const where = []; const args = [];
      if (subjectType) { where.push("subject_type = ?"); args.push(subjectType); }
      if (subjectType && subjectId !== undefined) { where.push("subject_id IS ?"); args.push(subjectId ?? null); }
      const sql = `SELECT * FROM conflict_check ${where.length ? "WHERE " + where.join(" AND ") : ""}
        ORDER BY checked_at DESC, rowid DESC`;
      return db.prepare(sql).all(...args);
    },
    conflictLatestCheck: (subjectType, subjectId) =>
      db.prepare(`SELECT * FROM conflict_check WHERE subject_type = ? AND subject_id IS ?
        ORDER BY checked_at DESC, rowid DESC LIMIT 1`).get(subjectType, subjectId ?? null) ?? null,
    conflictCountChecksBySubject: (subjectType) =>
      db.prepare("SELECT COUNT(*) AS n FROM conflict_check WHERE subject_type = ?").get(subjectType).n,
    conflictInsertHit: (rec) => db.prepare(`
      INSERT INTO conflict_hit (id, check_id, hit_type, target_type, target_id, matched_name, matched_field,
        matched_value, matched_ratio, match_level, severity, reason, stored_role, stored_standing)
      VALUES (@id, @check_id, @hit_type, @target_type, @target_id, @matched_name, @matched_field,
        @matched_value, @matched_ratio, @match_level, @severity, @reason, @stored_role, @stored_standing)`).run(rec),
    conflictListHitsByCheck: (checkId) =>
      db.prepare("SELECT * FROM conflict_hit WHERE check_id = ? ORDER BY rowid").all(checkId),
    // 证件盲索引密钥：同 audit.hmac 手法——首用生成 randomBytes(32) 落 app_meta 独立键
    // （键命名空间用途区分：盲索引密钥≠审计密钥≠AI 凭据）；密文列存 HMAC-SHA256 hex。
    conflictBlindOf: (() => {
      let cached = null;
      const META_KEY = "conflict.blindkey";
      return (normalizedId) => {
        const v = String(normalizedId ?? "").trim();
        if (!v) return null;
        if (!cached) {
          const row = db.prepare("SELECT value FROM app_meta WHERE key = ?").get(META_KEY);
          if (row) cached = Buffer.from(String(row.value), "base64");
          else {
            const fresh = randomBytes(32);
            db.prepare("INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value")
              .run(META_KEY, fresh.toString("base64"));
            cached = fresh;
          }
        }
        return createHmac("sha256", cached).update(v, "utf-8").digest("hex");
      };
    })(),
    // ── 功能 #13 法条手册（RE-13 §3.2）：收藏/夹/搜索历史存取（迁移 0016_lawbook）──
    lbListFolders: (workspaceKey) =>
      db.prepare("SELECT * FROM lawbook_fav_folders WHERE workspace_key = ? ORDER BY sort_order, created_at").all(workspaceKey),
    lbCreateFolder: (rec) => db.prepare(`
      INSERT INTO lawbook_fav_folders (workspace_key, folder_id, name, sort_order, created_at)
      VALUES (@workspace_key, @folder_id, @name, @sort_order, @created_at)`).run(rec),
    lbRenameFolder: (workspaceKey, folderId, name) =>
      db.prepare("UPDATE lawbook_fav_folders SET name = ? WHERE workspace_key = ? AND folder_id = ?").run(name, workspaceKey, folderId),
    lbFolderContentCount: (workspaceKey, folderId) =>
      db.prepare("SELECT COUNT(*) AS n FROM lawbook_fav_contents WHERE workspace_key = ? AND folder_id = ?").get(workspaceKey, folderId).n,
    // 删夹=级联连删夹内收藏条目（等量 FavoriteFolderView deleteFolder：无迁移无回收站）
    lbDeleteFolder: (workspaceKey, folderId) => {
      db.prepare("DELETE FROM lawbook_fav_contents WHERE workspace_key = ? AND folder_id = ?").run(workspaceKey, folderId);
      db.prepare("DELETE FROM lawbook_fav_folders WHERE workspace_key = ? AND folder_id = ?").run(workspaceKey, folderId);
    },
    lbReorderFolders: (workspaceKey, orderedIds) => {
      const q = db.prepare("UPDATE lawbook_fav_folders SET sort_order = ? WHERE workspace_key = ? AND folder_id = ?");
      db.exec("BEGIN IMMEDIATE");
      try {
        orderedIds.forEach((id, i) => q.run(i, workspaceKey, id));
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    lbListFavLaws: (workspaceKey) =>
      db.prepare("SELECT * FROM lawbook_fav_laws WHERE workspace_key = ? ORDER BY created_at DESC, rowid DESC").all(workspaceKey),
    lbCountFavLaw: (workspaceKey, lawId) =>
      db.prepare("SELECT COUNT(*) AS n FROM lawbook_fav_laws WHERE workspace_key = ? AND law_id = ?").get(workspaceKey, lawId).n,
    lbAddFavLaw: (rec) => db.prepare(`
      INSERT INTO lawbook_fav_laws (workspace_key, row_id, law_id, created_at)
      VALUES (@workspace_key, @row_id, @law_id, @created_at)`).run(rec),
    lbDeleteFavLawRows: (workspaceKey, lawId) =>
      db.prepare("DELETE FROM lawbook_fav_laws WHERE workspace_key = ? AND law_id = ?").run(workspaceKey, lawId),
    lbDeleteFavLawRow: (workspaceKey, rowId) =>
      db.prepare("DELETE FROM lawbook_fav_laws WHERE workspace_key = ? AND row_id = ?").run(workspaceKey, rowId),
    lbListFavContents: (workspaceKey) =>
      db.prepare("SELECT * FROM lawbook_fav_contents WHERE workspace_key = ? ORDER BY created_at DESC, rowid DESC").all(workspaceKey),
    lbAddFavContent: (rec) => db.prepare(`
      INSERT INTO lawbook_fav_contents (workspace_key, row_id, law_id, line, folder_id, created_at)
      VALUES (@workspace_key, @row_id, @law_id, @line, @folder_id, @created_at)`).run(rec),
    lbDeleteFavContentRow: (workspaceKey, rowId) =>
      db.prepare("DELETE FROM lawbook_fav_contents WHERE workspace_key = ? AND row_id = ?").run(workspaceKey, rowId),
    lbMoveFavContentRows: (workspaceKey, rowIds, folderId) => {
      const q = db.prepare("UPDATE lawbook_fav_contents SET folder_id = ? WHERE workspace_key = ? AND row_id = ?");
      db.exec("BEGIN IMMEDIATE");
      try {
        for (const id of rowIds) q.run(folderId, workspaceKey, id);
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    lbListHistory: (workspaceKey, scope, lawId, limit) => {
      if (scope === "standalone") {
        return db.prepare(`SELECT * FROM lawbook_search_history
          WHERE workspace_key = ? AND scope = 'standalone' AND law_id IS ? ORDER BY search_t DESC, rowid DESC LIMIT ?`)
          .all(workspaceKey, lawId ?? null, limit);
      }
      return db.prepare(`SELECT * FROM lawbook_search_history
        WHERE workspace_key = ? AND scope = 'shared' ORDER BY search_t DESC, rowid DESC LIMIT ?`).all(workspaceKey, limit);
    },
    lbGetHistoryByText: (workspaceKey, scope, lawId, text) =>
      db.prepare(`SELECT * FROM lawbook_search_history WHERE workspace_key = ? AND scope = ? AND law_id IS ? AND text = ?`)
        .get(workspaceKey, scope, lawId ?? null, text) ?? null,
    lbPutHistory: (rec) => db.prepare(`
      INSERT INTO lawbook_search_history (workspace_key, row_id, scope, law_id, text, search_t)
      VALUES (@workspace_key, @row_id, @scope, @law_id, @text, @search_t)`).run(rec),
    lbRefreshHistory: (workspaceKey, rowId, ts) =>
      db.prepare("UPDATE lawbook_search_history SET search_t = ? WHERE workspace_key = ? AND row_id = ?").run(ts, workspaceKey, rowId),
    lbDeleteHistoryRow: (workspaceKey, rowId) =>
      db.prepare("DELETE FROM lawbook_search_history WHERE workspace_key = ? AND row_id = ?").run(workspaceKey, rowId),
    lbClearHistory: (workspaceKey, scope, lawId) => {
      if (scope === "standalone") {
        db.prepare("DELETE FROM lawbook_search_history WHERE workspace_key = ? AND scope = 'standalone' AND law_id IS ?")
          .run(workspaceKey, lawId ?? null);
        return;
      }
      db.prepare("DELETE FROM lawbook_search_history WHERE workspace_key = ? AND scope = 'shared'").run(workspaceKey);
    },
    // ── 功能 #14 引证核验落账（RE-14 F4，迁移 0018_citation_checks）：只追加+倒序读取 ──
    cvAppendCheck: (rec) => db.prepare(`
      INSERT INTO citation_checks (id, requested_at, as_of, citation_text, status, code, verified_scoped, reasons_json)
      VALUES (@id, @requested_at, @as_of, @citation_text, @status, @code, @verified_scoped, @reasons_json)`).run(rec),
    cvListChecks: (limit) =>
      db.prepare(`SELECT id, requested_at AS requestedAt, as_of AS asOf, citation_text AS citationText,
        status, code, verified_scoped AS verifiedScoped, reasons_json AS reasonsJson
        FROM citation_checks ORDER BY requested_at DESC, rowid DESC LIMIT ?`)
        .all(limit)
        .map((r) => ({
          id: r.id, requestedAt: r.requestedAt, asOf: r.asOf,
          citationText: r.citationText, status: r.status, code: r.code ?? "",
          verifiedScoped: Boolean(r.verifiedScoped),
          reasons: JSON.parse(r.reasonsJson || "[]"),
        })),
    cvCountChecks: () => db.prepare("SELECT COUNT(*) AS n FROM citation_checks").get().n,
    // ── 功能 #6 材料上传解析（RE-6 §3）：材料/分块/附件/解析缓存 DAO（单源实现在 material_service）──
    materials: createMaterialDao(db),
    // ── 功能 #42 电子数据取证（RE-42 §3.1）：源/块锚/行面/聊天段/归类/候选/标注/批注/留痕 DAO ──
    edisc: createEdiscDao(db),
    // ── 功能 #32 整理与尽调（RE-32 §3）：任务/成果版本/字段模板/台账/清单/沿革 DAO（含 #6 材料表只读消费）──
    diligence: createDiligenceDao(db),
    // ── 【#21 安全层】工具决策审计（RE-21 增补 §3.3）：记录/按会话升序查询（单实例，桥内共用）──
    toolAudits: createToolAuditService(db),
    // 会话删除（B47 记录删除）：行+块索引+回执一并清，索引行打删除位
    deleteSession: (workspaceKey, sessionId) => {
      db.prepare("UPDATE sessions SET deleted = 1 WHERE workspace_key = ? AND session_id = ?").run(workspaceKey, sessionId);
      db.prepare("DELETE FROM session_rows WHERE workspace_key = ? AND session_id = ?").run(workspaceKey, sessionId);
      db.prepare("DELETE FROM document_chunks WHERE workspace_key = ? AND session_id = ?").run(workspaceKey, sessionId);
      db.prepare("DELETE FROM command_receipts WHERE workspace_key = ? AND session_id = ?").run(workspaceKey, sessionId);
    },
  };
}
function titleOfRel(rel) {
  const base = rel.includes("/") ? rel.slice(rel.lastIndexOf("/") + 1) : rel;
  return base.replace(/\.[^.]+$/u, "") || base;
}
