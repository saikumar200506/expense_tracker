# Expense Tracker

A FastAPI backend for sharing expenses within a group. Users can create groups, add members, record expenses, and see who owes whom. The additional feature is smart settlement suggestions, which can reduce the number of payments needed to clear a group's balances.

Built for the Decentro SDE Intern assignment using Python 3.11, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, and Alembic.

## Run locally

Prerequisites: Python 3.11 and a running PostgreSQL server. The project was developed with Python 3.11.9 and PostgreSQL 18.

Run the following commands from the repository root.

### 1. Create a virtual environment and install dependencies

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`, then run the same installation command.

### 2. Create a database

Connect to PostgreSQL through `psql` or the pgAdmin Query Tool using a role that can create databases, then run:

```sql
CREATE DATABASE expense_tracker;
```

### 3. Configure the connection

Create a `.env` file beside `main.py`:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expense_tracker
DB_USER=postgres
DB_PASSWORD=your_local_password
```

Replace the username and password with your local PostgreSQL credentials. The configured role needs permission to create tables in this database. `.env` is excluded from Git.

### 4. Apply migrations and start the API

```powershell
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to try the endpoints. The OpenAPI document is available at [openapi.json](http://127.0.0.1:8000/openapi.json).

`GET /health` returns `{"status":"Ok"}`. This checks that the application is running; the user and group endpoints also exercise the database connection.

To check for differences between the models and the database schema:

```powershell
python -m alembic check
```

## API

Base URL: `http://127.0.0.1:8000`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Check application health |
| POST | `/users` | Create a user |
| GET | `/users` | List users |
| POST | `/groups` | Create a group and add its creator as a member |
| GET | `/groups` | List groups with their creators' names |
| POST | `/groups/{group_id}/members` | Add an existing user to a group |
| GET | `/groups/{group_id}/members` | List group members |
| POST | `/groups/{group_id}/expenses` | Add an expense and save each member's share |
| GET | `/groups/{group_id}/expenses` | List expenses, newest first, with payer names |
| GET | `/groups/{group_id}/balances` | Return what each member owes other members |
| GET | `/groups/{group_id}/settlement-suggestions` | Suggest fewer payments when possible |

Group-specific operations take `group_id` in the path so the request body does not need to repeat it. IDs identify records; names are included in responses where they help users read the result.

Successful POST requests return `201 Created`. Successful GET requests return `200 OK`. List endpoints return arrays, including an empty array when there are no records.

### Example requests

Create a user with `POST /users`:

```json
{"name": "saikumar"}
```

Example response:

```json
{"id": 1, "name": "saikumar"}
```

Create a group with `POST /groups`:

```json
{"name": "Trip", "created_by": 1}
```

Example response:

```json
{"id": 1, "name": "Trip", "created_by": 1, "creator_name": "saikumar"}
```

The creator is already a member. After creating another user, add them with `POST /groups/1/members`:

```json
{"user_id": 2}
```

This returns the added user's `id` and `name`.

Record an expense with `POST /groups/1/expenses`:

```json
{
  "paid_by": 1,
  "amount": "1200.00",
  "description": "Breakfast"
}
```

The response includes `id`, `group_id`, `paid_by`, `payer_name`, `amount`, `description`, `split_type`, and `created_at`. Expense history returns the same fields for each expense. `split_type` is currently always `"equal"`.

Amounts accept JSON numbers or decimal strings. Responses use decimal strings, such as `"1200.00"`, to preserve exact monetary values. Use the IDs returned by your requests; example IDs assume a fresh database.

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

For example, adding a duplicate member returns:

```json
{"detail": "User is already a member of this group."}
```

## Architecture

```text
main.py          Creates the FastAPI app and registers routers
routers/         Handles user, group, expense, and balance requests
schemas.py       Defines request validation and response formats
services.py      Calculates equal shares, balances, and settlement plans
models.py        Defines tables, keys, indexes, and constraints
database.py      Loads configuration and provides database sessions
migrations/      Stores Alembic migrations
```

Routers validate referenced records and use SQLAlchemy sessions to read or write data. Money calculations live in `services.py` and do not depend on HTTP or database access.

An expense and all its split rows are saved in one transaction. If saving fails, the transaction is rolled back. Group creation and the creator's membership are also saved together. A database session is opened for each request that needs one and closed afterward.

## Database design

| Table | Columns | Purpose and constraints |
| --- | --- | --- |
| `users` | `id`, `name` | Primary key on `id`; unique index on the lowercase, trimmed name |
| `groups` | `id`, `name`, `created_by` | Creator references `users`; normalized name is unique per creator |
| `group_members` | `group_id`, `user_id` | Both are foreign keys; the pair is the primary key, preventing duplicate membership |
| `expenses` | `id`, `group_id`, `paid_by`, `amount`, `description`, `created_at`, `split_type` | References the group and payer; positive amount; timezone-aware timestamp |
| `expense_splits` | `expense_id`, `user_id`, `share_amount` | Both IDs are foreign keys; the pair is the primary key; share cannot be negative |

The membership and split tables use composite primary keys because each pair already identifies one record. They do not need separate IDs. Expenses have their own IDs, so descriptions such as "Dinner" can repeat.

A composite foreign key from `expenses(group_id, paid_by)` to `group_members(group_id, user_id)` ensures the payer belongs to the expense's group. The application selects the participants from that group's members and calculates shares whose total equals the expense amount. Participant membership and the total of the shares are checked by application logic; the database does not enforce those two rules across split rows.

Saving individual shares preserves the membership at the time of the expense. Adding a new member affects later expenses without changing earlier ones. It also leaves room for future custom splits. The database permits `equal` and `custom` as split types, but the current API implements equal splits only.

Balances are calculated from saved expenses and splits rather than stored separately, avoiding a second set of balance records that could become inconsistent.

## Assumptions and calculation rules

- Each name represents one user because this version has no email address or login. User names are unique across the system, ignoring case and surrounding spaces. Different creators can use the same group name.
- There is no authentication. The caller supplies `created_by`, `user_id`, and `paid_by`; these are checked against existing records but do not establish the caller's identity.
- All current group members participate in each new expense, including the payer. Groups support adding members; removing members and editing or deleting expenses are outside the current API.
- Amounts are treated as INR. There is no currency conversion. Amounts must be positive and fit `NUMERIC(12, 2)`, allowing up to ten digits before the decimal point and two after it.
- Python uses `Decimal` and PostgreSQL uses `NUMERIC(12, 2)` for money. Equal splitting temporarily converts the amount to integer paise to distribute the remainder exactly.

For example, INR 100.00 split between three members becomes 33.34, 33.33, and 33.33. Any extra paise go to members in ascending user ID order. This is repeatable and keeps the total exact, although lower IDs can receive the extra paisa on repeated uneven splits. A very small expense can give some members a zero share.

The payer's share is stored for the expense, but it does not create a debt to themselves. Opposite debts between the same two users are offset. If Mohit owes saikumar 600.00 and saikumar owes Mohit 250.00, the balance becomes Mohit owing saikumar 350.00. Every group member appears in the balance response; members who owe nothing have an empty `owes` object.

## Product enhancement: smart settlement suggestions

I chose this feature because a correct balance list can still leave a group making several payments. The suggestion endpoint looks for a way to clear the same net balances with fewer transfers.

For each member, it calculates the amount they should receive minus the amount they owe. It then repeatedly matches the largest remaining debtor with the largest remaining creditor and suggests the smaller of their outstanding amounts. Ties are resolved by user ID.

### Worked example

1. saikumar and mohit are members. saikumar pays 1200.00 for breakfast: each share is 600.00.
2. mohit pays 500.00 for a movie: each share is 250.00. mohit now owes saikumar 350.00.
3. rahul joins and pays 1500.00 for travel: the three members each owe a 500.00 share of this new expense.

`GET /groups/1/balances` returns:

```json
{
  "saikumar": {"owes": {"rahul": "500.00"}},
  "mohit": {"owes": {"saikumar": "350.00", "rahul": "500.00"}},
  "rahul": {"owes": {}}
}
```

There are three outstanding payments. saikumar's net position is to pay 150.00, mohit's is to pay 850.00, and rahul's is to receive 1000.00.

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

The counts refer to payments between users after opposite debts have been offset, not to the number of recorded expenses. The endpoint returns a plan only when it uses fewer payments than the existing balances. Otherwise, including when there are no outstanding balances, it returns `200 OK` with:

```json
{"message": "No meaningful settlement suggestions found."}
```

### Decisions and tradeoffs

The greedy algorithm is easy to follow and preserves everyone's net position. It does not guarantee the smallest possible number of payments. Comparing the candidate's count with the original count ensures the API only recommends a plan that reduces payments. Finding an exact minimum would require a more expensive search.

The current matching implementation scans the remaining debtors and creditors each round, taking O(n²) time and O(n) additional memory for n members. This is adequate for small groups; heaps could improve matching performance for larger groups.

A plan can change who someone pays while preserving how much each person owes or receives overall. It is a group-wide suggestion. Requesting it does not record payments or change stored balances. Recording actual repayments would need a separate settlement ledger.

## Verification

The API was checked through Swagger UI with user creation, duplicate names, group creation, duplicate membership, expense history, invalid amounts, and payer membership validation. The worked example above was checked after adding expenses and a new member.

Calculation checks covered uneven splits, amounts smaller than the member count, cancellation of opposite debts, no self-debt, and settlement plans preserving each member's net position. The applied migration and model schema were also checked for differences.

The repository does not currently include an automated test suite.

## Improvements with more time

- Add unit and API tests for expense creation, validation, rounding, and balances.
- Record actual settlements and include them when calculating outstanding balances.
- Add custom splits with participant validation and a check that all shares sum to the expense amount.
- Add authentication and a stable identity such as email, so different people can share a display name.
- Add Docker Compose for the API and PostgreSQL.
- Add pagination and indexes for group expense queries as the amount of data grows.
