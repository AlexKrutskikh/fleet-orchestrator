-- РОБОТЫ
CREATE TABLE robots (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              text NOT NULL UNIQUE,          -- два робота с одним именем — ошибка
    robot_type        text NOT NULL,                 -- 'csv_parser', 'report_generator'...
    status            text NOT NULL DEFAULT 'offline'
                      CHECK (status IN ('offline', 'idle', 'busy', 'paused', 'stopping')),
    host              text,                          -- может быть неизвестен, поэтому без NOT NULL
    last_heartbeat_at timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ЗАДАНИЯ: что нужно сделать
CREATE TABLE jobs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type     text NOT NULL,
    payload      jsonb NOT NULL DEFAULT '{}',        -- параметры задания, у разных типов разные
    priority     smallint NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    status       text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    max_attempts smallint NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    scheduled_at timestamptz NOT NULL DEFAULT now(), -- можно запланировать на будущее
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ЗАПУСКИ: одна попытка выполнения задания роботом
CREATE TABLE runs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id        bigint NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    robot_id      bigint REFERENCES robots (id) ON DELETE SET NULL,
    attempt       smallint NOT NULL CHECK (attempt > 0),
    status        text NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'succeeded', 'failed', 'timeout', 'cancelled')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    error_message text,
    UNIQUE (job_id, attempt),                        -- не бывает двух «вторых попыток»
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

-- КОМАНДЫ управления роботами
CREATE TABLE commands (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    robot_id        bigint NOT NULL REFERENCES robots (id) ON DELETE CASCADE,
    command_type    text NOT NULL
                    CHECK (command_type IN ('stop', 'kill', 'restart', 'pause', 'resume',
                                            'cancel_job', 'reload_config', 'ping')),
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('awaiting_approval', 'pending', 'sent', 'acknowledged',
                                      'done', 'failed', 'expired')),
    payload         jsonb NOT NULL DEFAULT '{}',
    idempotency_key uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    created_by      text NOT NULL,                   -- позже станет ссылкой на пользователя
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL DEFAULT now() + interval '5 minutes',
    completed_at    timestamptz
);

-- СОБЫТИЯ СТАТУСОВ: самая большая и быстро растущая таблица
CREATE TABLE status_events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id    uuid NOT NULL UNIQUE,                -- присваивает робот; защита от дублей
    robot_id    bigint NOT NULL REFERENCES robots (id) ON DELETE CASCADE,
    run_id      bigint REFERENCES runs (id) ON DELETE CASCADE,  -- heartbeat не относится к запуску
    event_type  text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}',
    occurred_at timestamptz NOT NULL,                -- когда случилось на роботе
    received_at timestamptz NOT NULL DEFAULT now()   -- когда дошло до нас
);

-- ИНДЕКСЫ
CREATE INDEX runs_robot_id_idx ON runs (robot_id);
CREATE INDEX commands_robot_pending_idx ON commands (robot_id)
    WHERE status IN ('pending', 'sent');
CREATE INDEX jobs_queue_idx ON jobs (priority DESC, scheduled_at)
    WHERE status = 'pending';
CREATE INDEX status_events_robot_time_idx ON status_events (robot_id, occurred_at DESC);