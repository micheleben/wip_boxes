import libmonzo
import pandas as pd
import datetime
import json
import os
import matplotlib.pyplot as plt
from collections import defaultdict

class MonzoExpenseTracker:
    def __init__(self, client_id, client_secret, owner_id, data_file="monzo_data.json", recurring_file="recurring_merchants.json"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.owner_id = owner_id
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
        
        # Get the first account
        accounts = self.client.accounts()
        if not accounts:
            raise Exception("No accounts found")
            
        account = accounts[0]
        print(f"Using account: {account.description}")
        
        # Fetch transactions
        since = datetime.datetime.now() - datetime.timedelta(days=days_back)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Use the Monzo API to get transactions
        transactions = self.client.transactions(account_id=account.identifier, since=since_str)
        
        print(f"Fetched {len(transactions)} transactions")
        
        # Convert to DataFrame
        transactions_data = []
        for tx in transactions:
            # Skip internal transfers and conversions
            if hasattr(tx, 'metadata') and tx.metadata.get('is_topup') == 'true':
                continue
                
            tx_data = {
                'id': tx.identifier,
                'date': tx.created,
                'description': tx.description,
                'amount': tx.amount / 100.0,  # Convert to main currency unit
                'currency': tx.currency,
                'category': tx.category,
                'merchant': tx.description,  # Use description as fallback for merchant
            }
            
            # If transaction has merchant info, use that
            if hasattr(tx, 'merchant') and tx.merchant:
                tx_data['merchant'] = tx.merchant.name
                
            transactions_data.append(tx_data)
            
        self.transactions_df = pd.DataFrame(transactions_data)
        
        # Convert date column to datetime
        self.transactions_df['date'] = pd.to_datetime(self.transactions_df['date'])
        
        # Sort by date
        self.transactions_df = self.transactions_df.sort_values('date')
        
        # Save transactions to file
        self.save_transactions()
        
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
        if self.transactions_df is None:
            print("No transactions loaded")
            return
            
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
        print(f"Recurring expenses: £{recurring_total:.2f} ({100 * recurring_total / total_spent:.1f}%)")
        print(f"Extra expenses: £{extra_total:.2f} ({100 * extra_total / total_spent:.1f}%)")
        
        # Summarize by category
        print("\n----- Spending by Category -----")
        category_totals = self.transactions_df[self.transactions_df['amount'] < 0].groupby('category')['amount'].sum().abs().sort_values(ascending=False)
        
        for category, amount in category_totals.items():
            print(f"{category}: £{amount:.2f} ({100 * amount / total_spent:.1f}%)")
            
        # Recurring merchants summary
        if len(recurring) > 0:
            print("\n----- Recurring Expenses -----")
            recurring_by_merchant = recurring.groupby('merchant')['amount'].sum().abs().sort_values(ascending=False)
            
            for merchant, amount in recurring_by_merchant.items():
                print(f"{merchant}: £{amount:.2f}")
                
        return {
            'total_spent': total_spent,
            'recurring_total': recurring_total,
            'extra_total': extra_total,
            'category_totals': category_totals.to_dict(),
            'recurring_by_merchant': recurring.groupby('merchant')['amount'].sum().abs().to_dict() if len(recurring) > 0 else {}
        }
        
    def visualize_expenses(self):
        """Create visualizations of expenses"""
        if self.transactions_df is None:
            print("No transactions loaded")
            return
            
        recurring, extra = self.categorize_expenses()
        summary = self.generate_summary()
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Pie chart of recurring vs extra
        ax1.pie(
            [summary['recurring_total'], summary['extra_total']],
            labels=['Recurring', 'Extra'],
            autopct='%1.1f%%',
            startangle=90
        )
        ax1.set_title('Recurring vs Extra Expenses')
        
        # Bar chart of top categories
        top_categories = pd.Series(summary['category_totals']).sort_values(ascending=False).head(5)
        top_categories.plot.bar(ax=ax2)
        ax2.set_title('Top 5 Expense Categories')
        ax2.set_ylabel('Amount (£)')
        
        plt.tight_layout()
        plt.savefig('expense_summary.png')
        print("Visualization saved to 'expense_summary.png'")
        
        # Monthly spending over time
        expenses = self.transactions_df[self.transactions_df['amount'] < 0].copy()
        expenses['month'] = expenses['date'].dt.to_period('M')
        monthly_spending = expenses.groupby(['month', 'is_recurring'])['amount'].sum().abs().unstack().fillna(0)
        
        plt.figure(figsize=(12, 6))
        monthly_spending.plot.bar(stacked=True)
        plt.title('Monthly Spending')
        plt.xlabel('Month')
        plt.ylabel('Amount (£)')
        plt.legend(['Extra', 'Recurring'])
        plt.tight_layout()
        plt.savefig('monthly_spending.png')
        print("Monthly spending visualization saved to 'monthly_spending.png'")

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
    else:
        # Get API credentials from user
        print("Please enter your Monzo API credentials:")
        client_id = input("Client ID: ")
        client_secret = input("Client Secret: ")
        owner_id = input("Owner ID: ")
        
        # Save config for next time
        with open(config_file, 'w') as f:
            json.dump({
                'client_id': client_id,
                'client_secret': client_secret,
                'owner_id': owner_id
            }, f)
    
    # Initialize tracker
    tracker = MonzoExpenseTracker(client_id, client_secret, owner_id)
    
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