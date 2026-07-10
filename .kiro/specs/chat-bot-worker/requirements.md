# Requirements Document

## Introduction

The **chat-bot-worker** is a backend daemon (`hybrid-router-cache/src/chat_worker.py`) that bridges the AMDChat Firebase Realtime Database frontend and the Python AI pipeline. When a human user posts a message to any chat room, the worker detects it, runs the message text through `run_pipeline(prompt)`, and writes a formatted bot reply back to the same chat room as "AMD Bot". The worker must be loop-safe (never reply to its own messages), must only process messages that arrive after it starts, and must surface pipeline cache metrics alongside the task plan in every reply.

---

## Glossary

- **Chat_Worker**: The Python daemon script (`src/chat_worker.py`) that listens for new user messages and dispatches bot replies.
- **Firebase_RTDB**: The Firebase Realtime Database instance accessed via `firebase_admin.db`, the same database the React frontend reads and writes.
- **Pipeline**: The function `run_pipeline(user_prompt: str) -> dict` in `src/pipeline.py` that runs Goal Understanding → Task Planning and returns `goal`, `tasks`, `cache_hits`, `tokens_used`, and `latency_sec`.
- **Bot_Message**: A message written to `/messages/{chatId}/{messageId}` by the Chat_Worker with `senderId: "bot"` and `senderName: "AMD Bot"`.
- **User_Message**: A message written to `/messages/{chatId}/{messageId}` by any sender whose `senderId` is not `"bot"`.
- **Startup_Timestamp**: The Unix epoch millisecond timestamp recorded by the Chat_Worker at the moment it begins listening. Messages with `timestamp` values less than or equal to this value are ignored.
- **Chat_Room**: A node at `/messages/{chatId}` in Firebase_RTDB containing a collection of messages for one conversation.
- **Task_Plan_Reply**: The formatted string the Chat_Worker writes as the `text` field of a Bot_Message, containing the pipeline goal, task list, and cache metrics.

---

## Requirements

### Requirement 1: Worker Startup and Initialization

**User Story:** As a developer, I want the Chat_Worker to initialize correctly on startup, so that it is ready to process incoming messages without crashing.

#### Acceptance Criteria

1. WHEN the Chat_Worker starts, THE Chat_Worker SHALL initialize the Firebase Admin SDK using the service-account credentials defined in `FIREBASE_KEY_PATH` before subscribing to any Firebase_RTDB paths.
2. WHEN the Chat_Worker starts, THE Chat_Worker SHALL record the Startup_Timestamp as the current Unix epoch in milliseconds.
3. WHEN the Chat_Worker starts, THE Chat_Worker SHALL attach a real-time listener to `/messages` in Firebase_RTDB that triggers on any child-added or child-changed event across all Chat_Rooms.
4. IF the Firebase Admin SDK fails to initialize due to missing or invalid credentials, THEN THE Chat_Worker SHALL print a descriptive error message to stderr and exit with a non-zero status code.
5. WHEN the Chat_Worker is running, THE Chat_Worker SHALL log a startup confirmation message to stdout that includes the Startup_Timestamp.

---

### Requirement 2: Message Filtering — Backlog Exclusion

**User Story:** As an operator, I want the Chat_Worker to ignore messages that existed before it started, so that it does not flood the chat with replies to old conversations on every restart.

#### Acceptance Criteria

1. WHEN a message event is received, THE Chat_Worker SHALL compare the message `timestamp` field to the Startup_Timestamp.
2. IF the message `timestamp` is less than or equal to the Startup_Timestamp, THEN THE Chat_Worker SHALL discard the event without calling the Pipeline or writing any Bot_Message.
3. WHEN a message event is received and the message has no `timestamp` field, THE Chat_Worker SHALL discard the event without processing it.

---

### Requirement 3: Message Filtering — Bot Loop Prevention

**User Story:** As an operator, I want the Chat_Worker to never reply to its own Bot_Messages, so that it does not create an infinite reply loop.

#### Acceptance Criteria

1. WHEN a message event is received, THE Chat_Worker SHALL inspect the `senderId` field of the message.
2. IF the `senderId` equals `"bot"`, THEN THE Chat_Worker SHALL discard the event without calling the Pipeline or writing any Bot_Message.
3. IF the message has no `senderId` field, THEN THE Chat_Worker SHALL discard the event without processing it.

---

### Requirement 4: Pipeline Invocation

**User Story:** As a user, I want the Chat_Worker to process my message through the AI pipeline, so that I receive an intelligent, context-aware reply.

#### Acceptance Criteria

1. WHEN a User_Message passes all filters (post-startup timestamp, non-bot sender, non-empty text), THE Chat_Worker SHALL invoke `run_pipeline(message.text)` from `src/pipeline.py`.
2. WHEN `run_pipeline` returns successfully, THE Chat_Worker SHALL use the returned `goal`, `tasks`, `cache_hits`, `tokens_used`, and `latency_sec` values to construct a Task_Plan_Reply.
3. IF `run_pipeline` raises an exception, THEN THE Chat_Worker SHALL catch the exception, log the error to stdout including the chat ID and message ID, and write a Bot_Message with a user-friendly error text (e.g., `"⚠️ Pipeline error — please try again."`) to the originating Chat_Room.
4. WHEN a User_Message has an empty or whitespace-only `text` field, THE Chat_Worker SHALL discard the event without calling the Pipeline.

---

### Requirement 5: Bot Reply Formatting

**User Story:** As a user, I want the bot reply to include the task plan and cache performance metrics, so that I can understand both the AI result and how efficiently it was computed.

#### Acceptance Criteria

1. WHEN constructing a Task_Plan_Reply, THE Chat_Worker SHALL include the pipeline `goal` summary as the first section of the reply text.
2. WHEN constructing a Task_Plan_Reply, THE Chat_Worker SHALL list each task from the `tasks` result as a numbered or bulleted line in the reply text.
3. WHEN constructing a Task_Plan_Reply, THE Chat_Worker SHALL include a metrics footer showing: goal cache status (`cache_hits.goal`), plan cache status (`cache_hits.plan`), total tokens used (`tokens_used`), and latency in seconds (`latency_sec`).
4. THE Chat_Worker SHALL format the Task_Plan_Reply as a plain UTF-8 string suitable for storage in the Firebase_RTDB `text` field without exceeding 10,000 characters.
5. WHERE the `tasks` result contains a list of task objects with a `description` or `task` field, THE Chat_Worker SHALL render each task's description text, not the raw dict representation.

---

### Requirement 6: Writing the Bot Reply to Firebase

**User Story:** As a user, I want the bot reply to appear in the same chat room I sent my message, so that the conversation feels natural.

#### Acceptance Criteria

1. WHEN the Task_Plan_Reply is ready, THE Chat_Worker SHALL write a new message node to `/messages/{chatId}` in Firebase_RTDB using `push()` to generate a unique message ID.
2. THE Chat_Worker SHALL set the following fields on every Bot_Message: `id` (the Firebase push key), `text` (the Task_Plan_Reply), `senderId` (`"bot"`), `senderName` (`"AMD Bot"`), `senderAvatarColor` (`"from-violet-500 to-indigo-500"`), `timestamp` (current Unix epoch in milliseconds).
3. WHEN a Bot_Message is written successfully, THE Chat_Worker SHALL also update `/chats/{chatId}` with `lastMessage` set to a truncated preview of the Task_Plan_Reply (first 100 characters) and `lastMessageTime` set to the Bot_Message timestamp.
4. IF writing the Bot_Message to Firebase_RTDB fails, THEN THE Chat_Worker SHALL log the error to stdout including the chat ID and retry once after a 2-second delay before giving up.

---

### Requirement 7: Concurrent Message Handling

**User Story:** As an operator, I want the Chat_Worker to handle multiple simultaneous incoming messages without blocking, so that busy chat rooms remain responsive.

#### Acceptance Criteria

1. WHEN multiple User_Messages arrive at the same time across different Chat_Rooms, THE Chat_Worker SHALL process each message in a separate thread so that one slow Pipeline call does not delay replies to other Chat_Rooms.
2. WHILE a Pipeline invocation is running for a given message, THE Chat_Worker SHALL continue listening for and dispatching other incoming messages.
3. THE Chat_Worker SHALL limit the maximum number of concurrent Pipeline threads to 10 to prevent resource exhaustion.

---

### Requirement 8: Graceful Shutdown

**User Story:** As an operator, I want the Chat_Worker to shut down cleanly on SIGINT or SIGTERM, so that I can stop the daemon without leaving orphaned threads or corrupted Firebase writes.

#### Acceptance Criteria

1. WHEN the Chat_Worker receives a SIGINT or SIGTERM signal, THE Chat_Worker SHALL stop accepting new messages for processing.
2. WHEN shutdown is initiated, THE Chat_Worker SHALL wait for all in-flight Pipeline threads to complete before exiting, up to a maximum of 30 seconds.
3. WHEN shutdown is complete, THE Chat_Worker SHALL log a shutdown confirmation message to stdout and exit with status code 0.
