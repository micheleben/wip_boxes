import libmonzo
import pandas as pd
import datetime
import json
import os
import matplotlib.pyplot as plt
from collections import defaultdict

class MonzoExpenseTracker:
    def __init__(self, client_id, client_secret, owner_id, account_id=None, data_file="monzo_data.json", recurring_file="recurring_merchants.json"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.owner_id = owner_id
        self.account_id = account_id  # Allow specifying account ID directly
        self.data_file = data_file
        self.recurring_file = recurring_file
        self.client = None
        self.transactions_df = None
        self.recurring_merchants = self.load_recurring_merchants()
        
    def authenticate(self):
        """Authenticate with Monzo API"""
        print("Authenticating with Monzo...")
        self.client = libmonzo.MonzoClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            owner_id=self.owner_id
        )
        
        # OAuth flow (will open browser window)
        self.client.authenticate()
        print("Authentication successful!")
        
    def fetch_transactions(self, days_back=90):
        """Fetch transactions from Monzo API"""
        if not self.client:
            raise Exception("Please authenticate first")
            
        print(f"Fetching transactions for the last {days_back} days...")
        
        # If account_id was provided directly, use it
        if self.account_id:
            account_id = self.account_id
            print(f"Using provided account ID: {account_id}")
        else:
            # Otherwise get accounts and find an active one
            accounts = self.client.accounts()
            print(f"Found {len(accounts)} accounts")
            
            if not accounts:
                raise Exception("No accounts found")
            
            # Find the first open account
            active_account = None
            for acc in accounts:
                print(f"Account: {acc.description}, Closed: {acc.is_closed}, Type: {acc.account_type}")
                if not acc.is_closed:
                    active_account = acc
                    break
                    
            # If no active account found, try to use any account
            if active_account is None:
                print("Warning: No open accounts found. Trying to use the first account anyway.")
                active_account = accounts[0]
                
            account_id = active_account.identifier
            print(f"Using account: {active_account.description}")
        
        print(f"Account ID: {account_id}")
        
        try:
            # Fetch all transactions first
            print("Fetching all available transactions...")
            transactions = self.client.transactions(account_id=account_id)
            print(f"Raw transactions count: {len(transactions)}")
            
            # Debug: Print first transaction if available
            if transactions:
                tx = transactions[0]
                print(f"Example transaction: {tx.description}, {tx.amount}, {tx.created}")
                
                for attr in dir(tx):
                    if not attr.startswith('_') and not callable(getattr(tx, attr)):
                        try:
                            print(f"Transaction.{attr} = {getattr(tx, attr)}")
                        except:
                            print(f"Transaction.{attr} = <error accessing>")
            
            # Then filter by date
            since = datetime.datetime.now() - datetime.timedelta(days=days_back)
            
            # Filter transactions by date
            filtered_transactions = []
            for tx in transactions:
                tx_date = pd.to_datetime(tx.created)
                if tx_date >= since:
                    filtered_transactions.append(tx)
            
            print(f"Fetched {len(filtered_transactions)} transactions from the last {days_back} days")
            
            # Handle the case with no transactions
            if not filtered_transactions:
                print("No transactions found in the specified time period.")
                # Create an empty DataFrame with the correct columns
                self.transactions_df = pd.DataFrame(columns=[
                    'id', 'date', 'description', 'amount', 'currency', 'category', 'merchant'
                ])
                return self.transactions_df
                
            # Convert to DataFrame
            transactions_data = []
            for tx in filtered_transactions:
                # Skip internal transfers and conversions
                if hasattr(tx, 'metadata') and tx.metadata.get('is_topup') == 'true':
                    continue
                    
                tx_data = {
                    'id': tx.identifier,
                    'date': tx.created,
                    'description': tx.description,
                    'amount': tx.amount / 100.0,  # Convert to main currency unit
                    'currency': tx.currency,
                    'category': getattr(tx, 'category', 'uncategorized'),
                    'merchant': tx.description,  # Use description as fallback for merchant
                }
                
                # If transaction has merchant info, use that
                if hasattr(tx, 'merchant') and tx.merchant:
                    tx_data['merchant'] = tx.merchant.name
                    
                transactions_data.append(tx_data)
            
            self.transactions_df = pd.DataFrame(transactions_data)
            
            # Check if we actually have data after filtering
            if len(self.transactions_df) == 0:
                print("No transactions found after filtering.")
                return self.transactions_df
            
            # Convert date column to datetime
            self.transactions_df['date'] = pd.to_datetime(self.transactions_df['date'])
            
            # Sort by date
            self.transactions_df = self.transactions_df.sort_values('date')
            
            # Save transactions to file
            self.save_transactions()
            
            return self.transactions_df
            
        except Exception as e:
            print(f"Error fetching transactions: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            
            # Create an empty DataFrame
            self.transactions_df = pd.DataFrame(columns=[
                'id', 'date', 'description', 'amount', 'currency', 'category', 'merchant'
            ])
            return self.transactions_df
    
    def load_transactions(self):
        """Load previously saved transactions"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                df = pd.DataFrame(data['transactions'])
                df['date'] = pd.to_datetime(df['date'])
                self.transactions_df = df
                print(f"Loaded {len(df)} transactions from file")
                return df
            except Exception as e:
                print(f"Error loading transactions: {e}")
                
        print("No saved transactions found")
        return None
    
    def save_transactions(self):
        """Save transactions to file"""
        if self.transactions_df is not None:
            # Convert to dict for JSON serialization
            transactions_dict = self.transactions_df.to_dict(orient='records')
            
            with open(self.data_file, 'w') as f:
                json.dump({'transactions': transactions_dict}, f)
                
            print(f"Saved {len(transactions_dict)} transactions to {self.data_file}")
    
    def load_recurring_merchants(self):
        """Load list of recurring merchants"""
        if os.path.exists(self.recurring_file):
            try:
                with open(self.recurring_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_recurring_merchants(self):
        """Save recurring merchants to file"""
        with open(self.recurring_file, 'w') as f:
            json.dump(self.recurring_merchants, f)
            
        print(f"Saved {len(self.recurring_merchants)} recurring merchants to {self.recurring_file}")
    
    def add_recurring_merchant(self, merchant):
        """Add a merchant to the recurring list"""
        if merchant not in self.recurring_merchants:
            self.recurring_merchants.append(merchant)
            self.save_recurring_merchants()
            print(f"Added '{merchant}' to recurring merchants")
    
    def remove_recurring_merchant(self, merchant):
        """Remove a merchant from the recurring list"""
        if merchant in self.recurring_merchants:
            self.recurring_merchants.remove(merchant)
            self.save_recurring_merchants()
            print(f"Removed '{merchant}' from recurring merchants")
    
    def identify_recurring_expenses(self):
        """Identify recurring expenses based on regular patterns"""
        if self.transactions_df is None:
            print("No transactions loaded")
            return
            
        # Only consider expenses (negative amounts)
        expenses = self.transactions_df[self.transactions_df['amount'] < 0].copy()
        
        # Count frequency of merchants
        merchant_counts = expenses['merchant'].value_counts()
        
        # Find potential recurring merchants (appear at least twice)
        potential_recurring = merchant_counts[merchant_counts >= 2].index.tolist()
        
        print("\nPotential recurring merchants found:")
        for i, merchant in enumerate(potential_recurring):
            print(f"{i+1}. {merchant} (appears {merchant_counts[merchant]} times)")
            
        # Ask user to confirm which merchants are recurring
        print("\nDo you want to add any of these merchants to your recurring list?")
        print("Enter the numbers separated by commas, or 'all' to add all, or 'skip' to skip:")
        
        choice = input().strip().lower()
        
        if choice == 'all':
            for merchant in potential_recurring:
                self.add_recurring_merchant(merchant)
        elif choice != 'skip':
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                for idx in indices:
                    if 0 <= idx < len(potential_recurring):
                        self.add_recurring_merchant(potential_recurring[idx])
            except:
                print("Invalid input, skipping")
    
    def categorize_expenses(self):
        """Categorize expenses into recurring and extra"""
        if self.transactions_df is None:
            print("No transactions loaded")
            return None, None
            
        # Only consider expenses (negative amounts)
        expenses = self.transactions_df[self.transactions_df['amount'] < 0].copy()
        
        # Mark recurring expenses
        expenses['is_recurring'] = expenses['merchant'].isin(self.recurring_merchants)
        
        # Split into recurring and extra expenses
        recurring = expenses[expenses['is_recurring']]
        extra = expenses[~expenses['is_recurring']]
        
        return recurring, extra
    
    def generate_summary(self):
        """Generate a summary of expenses"""
        if self.transactions_df is None or len(self.transactions_df) == 0:
            print("No transactions loaded or empty dataset")
            return {
                'total_spent': 0,
                'recurring_total': 0,
                'extra_total': 0,
                'category_totals': {},
                'recurring_by_merchant': {}
            }
            
        recurring, extra = self.categorize_expenses()
        
        print("\n===== EXPENSE SUMMARY =====")
        print(f"Total transactions: {len(self.transactions_df)}")
        print(f"Total expenses: {len(recurring) + len(extra)}")
        print(f"Recurring expenses: {len(recurring)}")
        print(f"Extra expenses: {len(extra)}")
        
        # Calculate totals
        total_spent = abs(self.transactions_df[self.transactions_df['amount'] < 0]['amount'].sum())
        recurring_total = abs(recurring['amount'].sum()) if len(recurring) > 0 else 0
        extra_total = abs(extra['amount'].sum()) if len(extra) > 0 else 0
        
        print(f"\nTotal spent: £{total_spent:.2f}")
        
        # Prevent division by zero
        if total_spent > 0:
            recurring_percent = 100 * recurring_total / total_spent
            extra_percent = 100 * extra_total / total_spent
            print(f"Recurring expenses: £{recurring_total:.2f} ({recurring_percent:.1f}%)")
            print(f"Extra expenses: £{extra_total:.2f} ({extra_percent:.1f}%)")
        else:
            print(f"Recurring expenses: £{recurring_total:.2f} (0.0%)")
            print(f"Extra expenses: £{extra_total:.2f} (0.0%)")
        
        # Summarize by category
        if total_spent > 0:
            print("\n----- Spending by Category -----")
            category_totals = self.transactions_df[self.transactions_df['amount'] < 0].groupby('category')['amount'].sum().abs().sort_values(ascending=False)
            
            for category, amount in category_totals.items():
                percent = 100 * amount / total_spent
                print(f"{category}: £{amount:.2f} ({percent:.1f}%)")
                
            # Recurring merchants summary
            if len(recurring) > 0:
                print("\n----- Recurring Expenses -----")
                recurring_by_merchant = recurring.groupby('merchant')['amount'].sum().abs().sort_values(ascending=False)
                
                for merchant, amount in recurring_by_merchant.items():
                    print(f"{merchant}: £{amount:.2f}")
                    
            category_totals_dict = category_totals.to_dict() if 'category_totals' in locals() else {}
            recurring_by_merchant_dict = recurring.groupby('merchant')['amount'].sum().abs().to_dict() if len(recurring) > 0 else {}
        else:
            category_totals_dict = {}
            recurring_by_merchant_dict = {}
        
        return {
            'total_spent': total_spent,
            'recurring_total': recurring_total,
            'extra_total': extra_total,
            'category_totals': category_totals_dict,
            'recurring_by_merchant': recurring_by_merchant_dict
        }
        
    def visualize_expenses(self):
        """Create visualizations of expenses"""
        if self.transactions_df is None or len(self.transactions_df) == 0:
            print("No transactions loaded or empty dataset - cannot generate visualizations")
            return
            
        recurring, extra = self.categorize_expenses()
        summary = self.generate_summary()
        
        if summary['total_spent'] == 0:
            print("No expenses to visualize")
            return
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Pie chart of recurring vs extra
        pie_data = [summary['recurring_total'], summary['extra_total']]
        # Only create pie chart if there's data
        if sum(pie_data) > 0:
            ax1.pie(
                pie_data,
                labels=['Recurring', 'Extra'],
                autopct='%1.1f%%',
                startangle=90
            )
            ax1.set_title('Recurring vs Extra Expenses')
        else:
            ax1.text(0.5, 0.5, 'No expenses to show', 
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=ax1.transAxes)
        
        # Bar chart of top categories
        if summary['category_totals']:
            top_categories = pd.Series(summary['category_totals']).sort_values(ascending=False).head(5)
            if not top_categories.empty:
                top_categories.plot.bar(ax=ax2)
                ax2.set_title('Top 5 Expense Categories')
                ax2.set_ylabel('Amount (£)')
            else:
                ax2.text(0.5, 0.5, 'No category data to show', 
                        horizontalalignment='center',
                        verticalalignment='center',
                        transform=ax2.transAxes)
        else:
            ax2.text(0.5, 0.5, 'No category data to show', 
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=ax2.transAxes)
        
        plt.tight_layout()
        plt.savefig('expense_summary.png')
        print("Visualization saved to 'expense_summary.png'")
        
        # Monthly spending over time
        expenses = self.transactions_df[self.transactions_df['amount'] < 0].copy()
        
        # Check if there are any expenses
        if len(expenses) > 0:
            expenses['month'] = expenses['date'].dt.to_period('M')
            monthly_spending = expenses.groupby(['month', 'is_recurring'])['amount'].sum().abs().unstack().fillna(0)
            
            # Only create chart if there's data
            if not monthly_spending.empty:
                plt.figure(figsize=(12, 6))
                monthly_spending.plot.bar(stacked=True)
                plt.title('Monthly Spending')
                plt.xlabel('Month')
                plt.ylabel('Amount (£)')
                plt.legend(['Extra', 'Recurring'])
                plt.tight_layout()
                plt.savefig('monthly_spending.png')
                print("Monthly spending visualization saved to 'monthly_spending.png'")
            else:
                print("No monthly spending data to visualize")
        else:
            print("No expenses data to create monthly visualization")

def main():
    print("=== Monzo Expense Tracker ===")
    
    # Check if config file exists
    config_file = 'monzo_config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        client_id = config.get('client_id')
        client_secret = config.get('client_secret')
        owner_id = config.get('owner_id')
        account_id = config.get('account_id')
    else:
        # Get API credentials from user
        print("Please enter your Monzo API credentials:")
        client_id = input("Client ID: ")
        client_secret = input("Client Secret: ")
        owner_id = input("Owner ID: ")
        account_id = input("Account ID (leave empty to auto-detect): ").strip() or None
        
        # Save config for next time
        with open(config_file, 'w') as f:
            json.dump({
                'client_id': client_id,
                'client_secret': client_secret,
                'owner_id': owner_id,
                'account_id': account_id
            }, f)
    
    # Initialize tracker
    tracker = MonzoExpenseTracker(client_id, client_secret, owner_id, account_id)
    
    # Try to load existing data
    transactions = tracker.load_transactions()
    
    # If no data or user wants to refresh, fetch new data
    if transactions is None or input("Do you want to fetch new transactions? (y/n): ").lower() == 'y':
        tracker.authenticate()
        days = int(input("How many days of transactions to fetch? (default: 90): ") or 90)
        tracker.fetch_transactions(days_back=days)
    
    while True:
        print("\n=== MENU ===")
        print("1. Identify recurring expenses")
        print("2. View expense summary")
        print("3. Visualize expenses")
        print("4. Manage recurring merchants")
        print("5. Fetch new transactions")
        print("6. Exit")
        
        choice = input("Enter your choice (1-6): ")
        
        if choice == '1':
            tracker.identify_recurring_expenses()
        elif choice == '2':
            tracker.generate_summary()
        elif choice == '3':
            tracker.visualize_expenses()
        elif choice == '4':
            print("\nCurrent recurring merchants:")
            for i, merchant in enumerate(tracker.recurring_merchants):
                print(f"{i+1}. {merchant}")
                
            print("\n1. Add merchant")
            print("2. Remove merchant")
            print("3. Back to main menu")
            
            subchoice = input("Enter your choice (1-3): ")
            
            if subchoice == '1':
                merchant = input("Enter merchant name: ")
                tracker.add_recurring_merchant(merchant)
            elif subchoice == '2':
                if not tracker.recurring_merchants:
                    print("No recurring merchants to remove")
                    continue
                    
                idx = int(input("Enter number to remove: ")) - 1
                if 0 <= idx < len(tracker.recurring_merchants):
                    tracker.remove_recurring_merchant(tracker.recurring_merchants[idx])
                else:
                    print("Invalid selection")
        elif choice == '5':
            tracker.authenticate()
            days = int(input("How many days of transactions to fetch? (default: 90): ") or 90)
            tracker.fetch_transactions(days_back=days)
        elif choice == '6':
            print("Goodbye!")
            break
        else:
            print("Invalid choice, please try again")

if __name__ == "__main__":
    main()