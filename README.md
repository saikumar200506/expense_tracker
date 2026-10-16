# Expense Tracker

Expense-sharing backend for the Decentro SDE Intern assignment. The API creates users and groups, manages group membership, records shared expenses, returns expense history, and calculates who owes whom. Smart settlement suggestions reduce the number of payments when possible.

Stack: Python 3.11, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, and Alembic. The project includes unit tests and Docker Compose support. The API implements equal splits; custom splits and recording repayments remain future work.

## Setup

Run all commands from the repository root. Choose Docker or a local Python environment.

### Docker

Start Docker Desktop with Linux containers enabled:

```sh
docker compose up --build
```

Compose builds the Python 3.11 API image and starts PostgreSQL 18. The API waits for the database health check, applies Alembic migrations, and starts on port 8000. Open [Swagger UI](http://127.0.0.1:8000/docs).

Compose supplies the API's `DB_*` settings; this setup requires no `.env` file. The API reaches PostgreSQL through the Docker network. Compose does not publish a database port on the host.

| Setting | Default | Override |
| --- | --- | --- |
| Database name | `expense_tracker` | `DOCKER_DB_NAME` |
| Database user | `expense_tracker` | `DOCKER_DB_USER` |
| Local development password | `expense_tracker_local` | `DOCKER_DB_PASSWORD` |
| Host API port | `8000` | `DOCKER_API_PORT` |

The Docker database starts empty on its first run. The `postgres_data` named volume retains its data across container stops. PostgreSQL applies the database credentials when it first initializes that volume.

If a local Uvicorn server already uses port 8000, stop it or select another host port. In PowerShell:

```powershell
$env:DOCKER_API_PORT = "8001"
docker compose up --build
```

Open `http://127.0.0.1:8001/docs`. Run subsequent Compose commands in the same terminal to retain the port override. Use another terminal in the repository root for status, logs, or shutdown commands; apply the same port override there if needed:

```sh
docker compose ps
docker compose logs api
docker compose down
```

`down` removes the containers and network but retains the database volume. Retain the volume to keep recorded expenses.

Run unit tests in a one-off API container:

```sh
docker compose run --build --rm --no-deps api python -m unittest discover -s tests -v
```

This command overrides the image's startup command and runs tests without starting PostgreSQL or applying migrations.

The Dockerfile runs the application as a non-root user. `.dockerignore` excludes local environments, credentials, Git history, and cached Python files from the build context. This single-instance setup runs migrations at API startup; multiple API instances should use a separate migration job.

### Local environment

Prerequisites: Python 3.11 and a running PostgreSQL server. Development used Python 3.11.9 and PostgreSQL 18.

#### 1. Create the environment and install dependencies

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

With the environment active, the remaining local commands work on all three platforms.

#### 2. Create the database

Connect through `psql` or the pgAdmin Query Tool with a role that can create databases:

```sql
CREATE DATABASE expense_tracker;
```

#### 3. Configure the connection

Create `.env` beside `main.py`:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expense_tracker
DB_USER=postgres
DB_PASSWORD=your_local_password
```

Set the username and password to local PostgreSQL credentials. The configured role needs permission to create tables in this database. Git excludes `.env`.

#### 4. Apply migrations and start the API

```sh
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs) for request and response schemas and interactive API documentation. The [OpenAPI document](http://127.0.0.1:8000/openapi.json) is available separately.

`GET /health` returns `{"status":"Ok"}`. This endpoint checks the application process; user and group endpoints also query the database.

Check for differences between model metadata and the applied database schema:

```sh
python -m alembic check
```

## API

Base URL: `http://127.0.0.1:8000`.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Check application health |
| POST | `/users` | Create a user |
| GET | `/users` | List users |
| POST | `/groups` | Create a group and add its creator as a member |
| GET | `/groups` | List groups with their creators' names |
| POST | `/groups/{group_id}/members` | Add an existing user to a group |
| GET | `/groups/{group_id}/members` | List group members |
| POST | `/groups/{group_id}/expenses` | Add an expense and save every current member's share |
| GET | `/groups/{group_id}/expenses` | List expenses, newest first, with payer names |
| GET | `/groups/{group_id}/balances` | Return what each member owes other members |
| GET | `/groups/{group_id}/settlement-suggestions` | Suggest fewer payments when possible |

Group-specific routes put `group_id` in the path; request bodies do not repeat it. IDs identify records. Responses include names for readability.

Successful POST requests return `201 Created`. Successful GET requests return `200 OK`. List endpoints return arrays, including an empty array when no records exist. Expense history sorts by `created_at` descending, then `id` descending.

### Requests and responses

Create a user with `POST /users`:

```json
{"name": "saikumar"}
```

Response:

```json
{"id": 1, "name": "saikumar"}
```

Create a group with `POST /groups`:

```json
{"name": "Trip", "created_by": 1}
```

Response:

```json
{"id": 1, "name": "Trip", "created_by": 1, "creator_name": "saikumar"}
```

The creator already belongs to the group. Create another user, then add that user with `POST /groups/1/members`:

```json
{"user_id": 2}
```

The response contains the added user's `id` and `name`.

Record an expense with `POST /groups/1/expenses`:

```json
{
  "paid_by": 1,
  "amount": "1200.00",
  "description": "Breakfast"
}
```

The response contains `id`, `group_id`, `paid_by`, `payer_name`, `amount`, `description`, `split_type`, and `created_at`. Expense history returns these fields for each expense. The current API always sets `split_type` to `"equal"`.

Amounts accept JSON numbers or decimal strings. Responses serialize monetary values as decimal strings, such as `"1200.00"`, to preserve exact values. Example IDs assume a fresh database; use the IDs returned by each request.

### Validation and errors

| Situation | Status |
| --- | --- |
| Blank user/group name, or a name longer than 100 characters | 422 |
| Duplicate user name, ignoring case and surrounding spaces | 409 |
| Duplicate group name for the same creator, using the same normalization | 409 |
| Adding someone who is already a group member | 409 |
| Referenced group, creator, user, or payer does not exist | 404 |
| Payer exists but is not a member of the group | 400 |
| Amount is zero, negative, non-finite, or outside the allowed precision | 422 |
| Blank expense description or nonpositive user ID in a request body | 422 |

Request schemas strip surrounding whitespace from names and descriptions before checking for blank values. `created_by`, `user_id`, and `paid_by` in request bodies must be positive integers.

Adding a duplicate member returns:

```json
{"detail": "User is already a member of this group."}
```

## Architecture

### Directory structure

```text
expense_tracker/
|-- main.py
|-- database.py
|-- models.py
|-- schemas.py
|-- services.py
|-- routers/
|   |-- __init__.py
|   |-- users.py
|   |-- groups.py
|   `-- expenses.py
|-- migrations/
|   |-- env.py
|   |-- README
|   |-- script.py.mako
|   `-- versions/
|       `-- 4a9f81fa800b_create_initial_expense_tracker_schema.py
|-- tests/
|   |-- __init__.py
|   |-- test_services.py
|   |-- test_schemas.py
|   `-- test_routes.py
|-- .env                  # Local configuration; ignored by Git
|-- .gitignore
|-- .dockerignore
|-- Dockerfile
|-- compose.yaml
|-- alembic.ini
|-- requirements.txt
`-- README.md
```

### Component responsibilities

```text
main.py          Creates the FastAPI app and registers routers
routers/         Handles user, group, expense, and balance requests
schemas.py       Defines request validation and response formats
services.py      Calculates equal shares, balances, and settlement plans
models.py        Defines tables, keys, indexes, and constraints
database.py      Loads configuration and provides database sessions
migrations/      Stores Alembic migrations
tests/           Unit tests for calculations, validation, and route handlers
Dockerfile       Builds the Python API image
compose.yaml     Runs the API and PostgreSQL with persistent database storage
```

Routers validate referenced records and use SQLAlchemy sessions to read and write data. `services.py` performs monetary calculations without HTTP or database dependencies. Each request that needs database access opens a session and closes it afterward.

### Transactions

Expense creation saves the expense and all split rows in one transaction. A save failure rolls back the transaction. Group creation saves the group and the creator's membership together.

## Database design

### Entity relationships

`PK` denotes a primary key; `FK` denotes a foreign key. `1 --< N` denotes one referenced row to zero or more referencing rows. The two PK columns in each join table form one composite primary key.

```text
+-------------------------------------+     +-------------------------------------+
| users                               |     | groups                              |
| PK id                               |1---N| PK id                               |
| name                                |     | name                                |
+-------------------------------------+     | FK created_by -> users.id           |
                  | 1                       +-------------------------------------+
                  |                                           | 1
                  v N                                         |
+-------------------------------------+                       |
| group_members                       |                       |
| PK/FK group_id -> groups.id          |                       |
| PK/FK user_id -> users.id            |                       |
+-------------------------------------+                       |
                  | 1                                         |
                  | composite payer membership                |
                  v N                                         v N
+---------------------------------------------------------------------------------+
| expenses                                                                        |
| PK id                                                                           |
| FK group_id -> groups.id                                                         |
| FK paid_by -> users.id                                                           |
| FK (group_id, paid_by) -> group_members(group_id, user_id)                         |
| amount, description, created_at, split_type                                      |
+---------------------------------------------------------------------------------+
                  | 1
                  v N
+-------------------------------------+
| expense_splits                      |
| PK/FK expense_id -> expenses.id      |
| PK/FK user_id -> users.id            |
| share_amount                        |
+-------------------------------------+
```

Foreign-key targets inside the boxes also identify the direct user relationships for expense payers and split participants, and the group relationship for memberships. The composite payer relationship references the entire `group_members(group_id, user_id)` key.

### Tables and constraints

| Table | Columns | Purpose and constraints |
| --- | --- | --- |
| `users` | `id`, `name` | Primary key on `id`; unique index on the lowercase, trimmed name |
| `groups` | `id`, `name`, `created_by` | Creator references `users`; normalized name is unique per creator |
| `group_members` | `group_id`, `user_id` | Both are foreign keys; the pair is the primary key, preventing duplicate membership |
| `expenses` | `id`, `group_id`, `paid_by`, `amount`, `description`, `created_at`, `split_type` | References the group and payer; positive amount; timezone-aware timestamp |
| `expense_splits` | `expense_id`, `user_id`, `share_amount` | Both IDs are foreign keys; the pair is the primary key; share cannot be negative |

All columns are non-null. PostgreSQL generates integer IDs for `users`, `groups`, and `expenses`. User and group names use `VARCHAR(100)`, descriptions use `TEXT`, and `split_type` uses `VARCHAR(20)`. Monetary columns use `NUMERIC(12, 2)`. The database supplies `created_at` with `now()` and stores a timezone-aware timestamp.

| Index or constraint | Rule |
| --- | --- |
| `uq_users_normalized_name` | Unique `lower(TRIM(BOTH FROM name))` across users |
| `uq_groups_creator_normalized_name` | Unique creator and lowercase, trimmed group name |
| `group_members` primary key | Unique `(group_id, user_id)` pair |
| `expense_splits` primary key | Unique `(expense_id, user_id)` pair |
| `fk_expenses_payer_membership` | `expenses(group_id, paid_by)` references `group_members(group_id, user_id)` |
| `ck_expenses_amount_positive` | `amount > 0` |
| `ck_expenses_split_type` | `split_type IN ('equal', 'custom')`; default is `equal` |
| `ck_expense_splits_share_nonnegative` | `share_amount >= 0` |

The unique indexes compare lowercase, trimmed names; request schemas also strip surrounding whitespace. Different creators can reuse a group name.

### Design decisions

Membership and split tables use composite primary keys because each pair identifies one record. They need no separate IDs. Expenses use their own IDs, so descriptions such as "Dinner" can repeat.

The composite foreign key enforces payer membership at the database level. The application selects split participants from the expense's group and calculates shares that sum to the expense amount. Participant membership and the total of the shares are application checks; the database does not enforce either rule across split rows.

Stored split rows preserve the members and shares at expense creation. Adding a member affects later expenses without changing earlier ones. The schema can support future custom splits: the database permits `equal` and `custom`, while the API currently implements equal splits only.

The service calculates balances from saved expenses and splits. It does not maintain a second set of balance records that could diverge from the expense history.

## Assumptions and business rules

### Identity and group membership

- Each name represents one user because the API has no email address or login. User names are globally unique, ignoring case and surrounding spaces.
- Group names are unique per creator under the same normalization. Different creators can use the same group name.
- The API has no authentication. Callers supply `created_by`, `user_id`, and `paid_by`. The API checks these IDs against existing records; the IDs do not establish the caller's identity.
- Every current group member participates in a new expense, including the payer. The creator automatically joins the group.
- The API supports adding members. Removing members and editing or deleting expenses remain outside its current scope.

### Amounts and equal splits

- All amounts represent INR; the service performs no currency conversion.
- Amounts must be positive and fit `NUMERIC(12, 2)`: at most ten digits before the decimal point and two after it. The largest supported expense is 9999999999.99.
- Python uses `Decimal`; PostgreSQL uses `NUMERIC(12, 2)`. Equal splitting temporarily converts the amount to integer paise.
- The splitter divides the paise equally, then distributes remaining paise in ascending user ID order. The shares sum exactly to the expense amount and differ by at most one paisa.

INR 100.00 split among three members produces 33.34, 33.33, and 33.33. The lowest user ID receives the extra paisa. This deterministic rule can assign the extra paisa to lower IDs repeatedly. A very small expense can leave some members with a zero share.

### Balances

The service stores the payer's share but excludes self-debt from balance calculations. It offsets opposite debts between the same two users: if Mohit owes saikumar 600.00 and saikumar owes Mohit 250.00, Mohit owes saikumar 350.00 after offsetting.

Every group member appears in the response. Members who owe nothing have an empty `owes` object. These pairwise balances preserve the original counterparties; the settlement feature can reroute payments across the group.

## Product enhancement: smart settlement suggestions

### Purpose

A pairwise balance list can require several payments even when the group can clear the same net positions with fewer transfers. Smart settlement suggestions address this payment overhead while preserving the amount each member owes or receives overall.

### Algorithm

1. Calculate each member's net position: amounts receivable minus amounts owed.
2. Match the largest remaining debtor with the largest remaining creditor. Resolve ties by user ID.
3. Suggest the smaller of their outstanding amounts and reduce both remaining balances.
4. Repeat until all net balances reach zero.
5. Return the candidate only when its payment count is lower than the existing pairwise payment count.

The settlement helper requires net positions to sum to zero. A suggestion changes no stored balance and records no payment.

### Worked example

1. saikumar and mohit belong to the group. saikumar pays 1200.00 for breakfast; each share is 600.00.
2. mohit pays 500.00 for a movie; each share is 250.00. mohit now owes saikumar 350.00.
3. rahul joins and pays 1500.00 for travel. Each of the three members has a 500.00 share of this new expense.

`GET /groups/1/balances` returns:

```json
{
  "saikumar": {"owes": {"rahul": "500.00"}},
  "mohit": {"owes": {"saikumar": "350.00", "rahul": "500.00"}},
  "rahul": {"owes": {}}
}
```

These balances require three payments. The net positions are saikumar paying 150.00, mohit paying 850.00, and rahul receiving 1000.00.

`GET /groups/1/settlement-suggestions` returns:

```json
{
  "original_payment_count": 3,
  "suggested_payment_count": 2,
  "payments_saved": 1,
  "suggestions": {
    "saikumar": {"pay": {"rahul": "150.00"}},
    "mohit": {"pay": {"rahul": "850.00"}},
    "rahul": {"pay": {}}
  }
}
```

The counts measure outstanding payments between users after opposite debts have been offset, not the number of recorded expenses. If the candidate uses the same number of payments or more, or no balances remain, the endpoint returns `200 OK` with:

```json
{"message": "No meaningful settlement suggestions found."}
```

Circular debts whose net positions all cancel can produce a zero-payment suggestion that removes the original outstanding payments.

### Tradeoffs

The greedy algorithm is straightforward and preserves every member's net position. It does not guarantee the globally smallest payment count. Comparing the candidate with the existing count ensures the API recommends only a reduction. An exact minimum requires a more expensive search.

The implementation scans the remaining debtors and creditors each round: O(n^2) time and O(n) additional memory for n members. This suits small groups; heaps could improve matching performance for larger groups.

Suggestions can change counterparties while preserving each member's total obligation or receivable. The plan applies to the group as a whole. Recording repayments and updating outstanding balances requires a separate settlement ledger.

## Tests and verification

### Unit tests

With the virtual environment active, run:

```sh
python -m unittest discover -s tests -v
```

The suite uses Python's built-in `unittest`; it requires no additional test packages.

| File | Coverage |
| --- | --- |
| `tests/test_services.py` | Equal shares, remainder paise, opposite debts, net balances, and settlement correctness |
| `tests/test_schemas.py` | Required fields, name and description validation, positive IDs, and amount precision |
| `tests/test_routes.py` | Expense creation, membership checks, saved shares, rollback on save failures, and settlement suggestion responses |

Route handler tests use mock database sessions and require neither a running PostgreSQL server nor a `.env` file. Database constraints, migrations, and the full HTTP request/response flow require separate integration tests.

### Manual verification

Swagger checks covered user creation, duplicate names, group creation, duplicate membership, expense history, invalid amounts, and payer membership validation. The worked example was verified after adding expenses and a new member.

Calculation checks covered uneven splits, amounts smaller than the member count, cancellation of opposite debts, no self-debt, and settlement plans preserving each member's net position. Schema checks compared the applied migration against model metadata.

Docker verification covered the image build, API startup, health and user endpoints, and 42 passing unit tests inside the API container.

## Improvements with Time

- Add API and PostgreSQL integration tests for routing, database constraints, and transactions.
- Record actual settlements and include them in outstanding balance calculations.
- Add custom splits with participant validation and a check that all shares sum to the expense amount.
- Add authentication and a stable identity such as email so different people can share a display name.
- Run migrations in a separate job and add deployment configuration for multiple API instances.
- Add pagination and indexes for group expense queries as data grows.
