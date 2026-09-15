from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
import datetime
from enum import Enum
from sqlalchemy import Column, Text
from utils.procedures import generate_user_id, generate_ver_token, generate_random_number, generate_thread_id


class UserType(str, Enum):
    NORMAL_USER = 'normal_user'
    ADMIN_USER = 'admin_user'


class User(SQLModel, table=True):
    __tablename__ = 'users'

    id: Optional[str] = Field(primary_key=True, index=True, nullable=False, default_factory=generate_user_id)
    name: str
    image: Optional[str]
    email: str = Field(index=True, unique=True)
    password: Optional[str]
    google_user_id: Optional[str]
    google_token: Optional[str]
    user_type: Optional[str] = Field(default=UserType.NORMAL_USER, nullable=False)
    is_email_verified: bool = Field(default=False)
    is_blocked: bool = Field(default=False)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    login_sessions: List['LoginSession'] = Relationship(back_populates='user')
    threads: List['Thread'] = Relationship(back_populates='user')


class LoginSessionTypes(str, Enum):
    WINDOWS = 'windows'
    MAC = 'mac'
    LINUX = 'linux'
    MOBILE = 'mobile'


class LoginSession(SQLModel, table=True):
    __tablename__ = 'login_sessions'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    user_id: str = Field(foreign_key='users.id')
    notification_token: Optional[str]
    expires_at: datetime.datetime
    refresh_expires_at: datetime.datetime
    login_session_type: Optional[str] = Field(default=LoginSessionTypes.WINDOWS)
    is_logged_out: bool = Field(default=False)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    user: Optional['User'] = Relationship(back_populates='login_sessions')


class EmailVerificationEntry(SQLModel, table=True):
    __tablename__ = 'email_verification_entries'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    email: str = Field(unique=True, index=True)
    verification_token: str = Field(default_factory=generate_ver_token)
    verification_code: str = Field(default_factory=generate_random_number)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})
    expires_at: datetime.datetime


class ThreadStatus(str, Enum):
    STANDBY = 'standby'
    WORKING = 'working'
    ERROR = 'error'
    DELETED = 'deleted'


class Thread(SQLModel, table=True):
    __tablename__ = 'threads'

    id: Optional[str] = Field(primary_key=True, index=True, nullable=False, default_factory=generate_thread_id)
    title: str = Field(nullable=False)
    user_id: str = Field(foreign_key='users.id')
    status: Optional[str] = Field(nullable=False, default=ThreadStatus.STANDBY)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    user: Optional['User'] = Relationship(back_populates='threads')
    thread_tasks: List['ThreadTask'] = Relationship(back_populates='thread')
    thread_messages: List['ThreadMessage'] = Relationship(back_populates='thread')


class ThreadTaskStatus(str, Enum):
    WORKING = 'working'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELED = 'canceled'


class ThreadTask(SQLModel, table=True):
    __tablename__ = 'thread_tasks'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    thread_id: str = Field(nullable=False, foreign_key='threads.id')
    status: Optional[str] = Field(nullable=False, default=ThreadTaskStatus.WORKING)
    task_text: str = Field(sa_column=Column(Text, nullable=True))
    needs_memory_from_previous_tasks: bool = Field(default=False)
    background_mode: bool = Field(default=False)
    extended_thinking_mode: bool = Field(default=False)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    thread: Optional['Thread'] = Relationship(back_populates='thread_tasks')
    thread_task_messages: List['ThreadMessage'] = Relationship(back_populates='thread_task')
    plans: List['ThreadTaskPlan'] = Relationship(back_populates='thread_task')
    memory_entries: List['ThreadTaskMemoryEntry'] = Relationship(back_populates='thread_task')


class ThreadTaskPlanStatus(str, Enum):
    ACTIVE = 'active'
    COMPLETED = 'completed'
    CANCELED = 'canceled'
    FAILED = 'failed'
    REPLACED = 'replaced'


class ThreadTaskPlan(SQLModel, table=True):
    __tablename__ = 'thread_task_plans'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    thread_task_id: Optional[int] = Field(nullable=True, foreign_key='thread_tasks.id')
    status: Optional[str] = Field(nullable=False, default=ThreadTaskPlanStatus.ACTIVE)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    thread_task: Optional['ThreadTask'] = Relationship(back_populates='plans')
    subtasks: List['PlanSubtask'] = Relationship(back_populates='plan')


class SubtaskStatus(str, Enum):
    ACTIVE = 'active'
    COMPLETED = 'completed'
    CANCELED = 'canceled'
    FAILED = 'failed'


class SubtaskType(str, Enum):
    DESKTOP = 'desktop'
    # Deprecated BROWSER = 'browser'


class PlanSubtask(SQLModel, table=True):
    __tablename__ = 'plan_subtasks'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    thread_task_plan_id: Optional[int] = Field(nullable=True, foreign_key='thread_task_plans.id')
    subtask_text: str = Field(sa_column=Column(Text, nullable=False))
    subtask_type: str = Field(default=SubtaskType.DESKTOP, nullable=False)
    ordering: Optional[int] = Field(nullable=False, default=0)
    status: Optional[str] = Field(nullable=False, default=SubtaskStatus.ACTIVE)

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    plan: Optional['ThreadTaskPlan'] = Relationship(back_populates='subtasks')
    plan_subtask_messages: List['ThreadMessage'] = Relationship(back_populates='plan_subtask')


class ThreadTaskMemoryEntry(SQLModel, table=True):
    __tablename__ = 'thread_task_memory_entries'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    thread_task_id: Optional[int] = Field(nullable=True, foreign_key='thread_tasks.id')
    text: str = Field(sa_column=Column(Text, nullable=False))

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    thread_task: Optional['ThreadTask'] = Relationship(back_populates='memory_entries')


class ThreadChatType(str, Enum):
    NORMAL_MESSAGE = 'normal_message'
    CLASSIFICATION = 'classification'
    THINKING = 'thinking'
    PLAN = 'plan'
    ACTION = 'action'
    # BROWSER_USE = 'browser_use' Deprecated
    # DESKTOP_USE = 'desktop_use' Deprecated
    DESKTOP_USE = 'desktop_use_v2'
    # BACKGROUND_MODE_BROWSER = 'bg_mode_browser' # Deprecated
    BACKGROUND_MODE_BROWSER = 'bg_mode_browser_v2'


class ThreadChatFromChoices(str, Enum):
    FROM_USER = 'from_user'
    FROM_AI = 'from_ai'


class ThreadMessage(SQLModel, table=True):
    __tablename__ = 'thread_messages'

    id: Optional[int] = Field(primary_key=True, index=True, nullable=False)
    thread_id: str = Field(nullable=False, foreign_key='threads.id')
    thread_task_id: Optional[int] = Field(nullable=True, foreign_key='thread_tasks.id')
    plan_subtask_id: Optional[int] = Field(nullable=True, foreign_key='plan_subtasks.id')
    thread_chat_type: str = Field(nullable=False, default=ThreadChatType.NORMAL_MESSAGE)
    thread_chat_from: str = Field(nullable=False, default=ThreadChatFromChoices.FROM_USER)
    text: str = Field(sa_column=Column(Text, nullable=True))
    chain_of_thought: Optional[str] = Field(sa_column=Column(Text, nullable=True))
    # Saving Data for Further Model Training
    screenshot: Optional[str]
    prompt: Optional[str] = Field(sa_column=Column(Text, nullable=True))

    created_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now)
    updated_at: Optional[datetime.datetime] = Field(default_factory=datetime.datetime.now,
                                                    sa_column_kwargs={'onupdate': datetime.datetime.now})

    thread: Optional['Thread'] = Relationship(back_populates='thread_messages')
    thread_task: Optional['ThreadTask'] = Relationship(back_populates='thread_task_messages')
    plan_subtask: Optional['PlanSubtask'] = Relationship(back_populates='plan_subtask_messages')
