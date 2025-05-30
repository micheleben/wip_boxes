# Monzo Playground Tools

These scripts provide a way for a user to connect to their Monzo account (using a developer access token), download their transaction history, identify and manage recurring payments, and get summaries and visualizations of their spending habits. It's a personal finance tool focused on Monzo bank data.

## monzo_playground_token.py

This Python script, monzo_playground_token.py, is designed to be a Monzo Expense Tracker that interacts directly with the Monzo API using a pre-obtained access token (likely from the Monzo API Playground).

Here's a breakdown of what it does:

1. **Direct API Interaction:**

    *   It uses the requests library to make direct HTTP calls to the Monzo API (https://api.monzo.com).
    * It requires an access_token and account_id for authentication and to specify which account's transactions to fetch. These are initially loaded from a 'monzo_config.json' file or prompted from the user if the file doesn't exist.
    monzo_direct_config.json file or, if the file doesn't exist, prompted from the user and then saved.
2. **Transaction Fetching:**

    The fetch_transactions method retrieves transactions for the specified account.
    * It can fetch all transactions and then filters them locally for a specified number of past days (defaulting to 90).
    * It includes an expand[]=merchant parameter in the API call to get detailed merchant information.
    * It handles potential API errors and creates an empty DataFrame if fetching fails.
    * It skips transactions marked as 'topup' in their metadata (internal transfers/conversions).
    The fetched transaction data (ID, date, description, amount, currency, category, merchant name) is converted into a Pandas DataFrame.
3. **Data Storage and Loading:**

   * Fetched transactions are saved locally to a JSON file (monzo_data.json). The date is converted to a string format (%Y-%m-%dT%H:%M:%SZ) before saving.
   * The script can load previously saved transactions from this file using load_transactions, converting the date strings back to datetime objects. This avoids re-fetching data every time.

4. **Recurring Expense Management:**

   * It allows users to define a list of "recurring merchants." This list is stored in recurring_merchants.json.
   * The identify_recurring_expenses method analyzes transactions, counts merchant occurrences, and suggests potential recurring merchants (those appearing at least twice). The user can then choose to add these to their recurring list.
   * Users can manually add or remove merchants from the recurring list.
     
5. **Expense Categorization and Summary:**

    * categorize_expenses splits expenses (transactions with negative amounts) into "recurring" (based on the recurring_merchants list) and "extra."
    * generate_summary provides a text-based summary, including:
    * Total transactions, total expenses, number of recurring and extra expenses.
    * Total amount spent.
    * Breakdown of recurring vs. extra expenses (amount and percentage).
    * Spending by category (amount and percentage).
    * A list of recurring expenses by merchant and their total amounts.
    * It handles cases with no transactions or no expenses gracefully.
6. **Expense Visualization:**

    * visualize_expenses uses matplotlib to create and save two plots:
    * expense_summary.png: A figure with two subplots:
    * A pie chart showing the proportion of recurring vs. extra expenses.
    * A bar chart showing the top 5 expense categories.
    * monthly_spending.png: A stacked bar chart showing monthly spending, broken down into recurring and extra.
    * It also handles cases where there's no data to visualize.
7. **Command-Line Interface (CLI):**

    *   The main() function provides a simple menu-driven CLI for users to interact with the tracker.
    * Options include:
        * Identifying recurring expenses.
        * Viewing the expense summary.
        * Visualizing expenses.
        * Managing the list of recurring merchants (add/remove).
        * Fetching new transactions.
        * Exiting the application.

## script_to_check_monzo_v11.py

This Python script, `script_to_check_monzo_v11.py`, is a **Monzo Expense Tracker** that uses the `libmonzo` library to interact with the Monzo API. It's designed to help users fetch, analyze, and visualize their Monzo bank transactions.

Here's a breakdown of its functionality:

1.  **Authentication via `libmonzo`:**
    *   It uses the `libmonzo` library to handle the OAuth 2.0 authentication flow with Monzo. This is a more robust and standard way to authenticate compared to using a static playground token.
    *   The `authenticate` method initiates this flow, which typically involves opening a web browser for the user to grant permission.
    *   It requires `client_id`, `client_secret`, and `owner_id` for authentication. These are loaded from a `monzo_config.json` file or prompted from the user if the file doesn't exist.

2.  **Account Selection:**
    *   The script can either use an `account_id` provided during initialization or, if not provided, it will fetch all accounts associated with the authenticated user.
    *   It then attempts to find the first "open" (not closed) account to use. If no open accounts are found, it defaults to using the first account in the list with a warning.

3.  **Transaction Fetching:**
    *   The `fetch_transactions` method retrieves transactions for the selected account using the `libmonzo` client.
    *   It fetches *all* available transactions for the account first and then filters them locally for a specified number of past days (defaulting to 90).
    *   It includes debugging output for the first transaction's attributes.
    *   It skips transactions marked as 'topup' in their metadata (internal transfers/conversions).
    *   The fetched transaction data (ID, date, description, amount, currency, category, merchant name) is converted into a Pandas DataFrame. Merchant name is taken from `tx.merchant.name` if available, otherwise, it falls back to `tx.description`.
    *   It handles potential errors during fetching and creates an empty DataFrame if an issue occurs.

4.  **Data Storage and Loading:**
    *   Fetched transactions are saved locally to a JSON file (`monzo_data.json`). The date is converted to a string format before saving.
    *   The script can load previously saved transactions from this file using `load_transactions`, converting date strings back to datetime objects. This avoids re-fetching data every time.

5.  **Recurring Expense Management:**
    *   It allows users to define a list of "recurring merchants." This list is stored in `recurring_merchants.json`.
    *   The `identify_recurring_expenses` method analyzes transactions, counts merchant occurrences, and suggests potential recurring merchants (those appearing at least twice). The user can then choose to add these to their recurring list.
    *   Users can manually add or remove merchants from the recurring list via the CLI.

6.  **Expense Categorization and Summary:**
    *   `categorize_expenses` splits expenses (transactions with negative amounts) into "recurring" (based on the `recurring_merchants` list) and "extra."
    *   `generate_summary` provides a text-based summary, including:
        *   Total transactions, total expenses, number of recurring and extra expenses.
        *   Total amount spent.
        *   Breakdown of recurring vs. extra expenses (amount and percentage).
        *   Spending by category (amount and percentage).
        *   A list of recurring expenses by merchant and their total amounts.
    *   It handles cases with no transactions or no expenses gracefully.

7.  **Expense Visualization:**
    *   `visualize_expenses` uses `matplotlib` to create and save two plots:
        *   `expense_summary.png`: A figure with two subplots:
            *   A pie chart showing the proportion of recurring vs. extra expenses.
            *   A bar chart showing the top 5 expense categories.
        *   `monthly_spending.png`: A stacked bar chart showing monthly spending, broken down into recurring and extra.
    *   It also handles cases where there's no data to visualize.

8.  **Command-Line Interface (CLI):**
    *   The `main()` function provides a simple menu-driven CLI for users to interact with the tracker.
    *   Options include:
        *   Identifying recurring expenses.
        *   Viewing the expense summary.
        *   Visualizing expenses.
        *   Managing the list of recurring merchants (add/remove).
        *   Fetching new transactions (which re-authenticates if necessary).
        *   Exiting the application.

In essence, this script is a more complete Monzo expense tracking application compared to one that might use a simple playground token. It leverages the `libmonzo` library for proper authentication and API interaction, allowing users to connect to their Monzo account, download transactions, manage recurring payments, and get insights into their spending through summaries and visualizations.

