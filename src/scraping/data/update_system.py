"""
Simple Update System for Lotto 6/49 Dataset
Add new draws to the historical dataset
"""

import pandas as pd

def add_new_draw():
    """Manually add a new draw to the dataset"""
    df = pd.read_csv('lotto_649_complete.csv')
    
    print("➕ ADD NEW LOTTO 6/49 DRAW")
    print("=" * 40)
    
    # Get date
    date = input("Draw date (e.g., 'November 22, 2025'): ").strip()
    
    # Get numbers
    numbers = []
    for i in range(1, 7):
        while True:
            num = input(f"Number {i} (1-49): ").strip()
            if num.isdigit() and 1 <= int(num) <= 49:
                numbers.append(int(num))
                break
            else:
                print("Invalid! Enter number 1-49.")
    
    # Get bonus
    while True:
        bonus = input("Bonus number (1-49): ").strip()
        if bonus.isdigit() and 1 <= int(bonus) <= 49:
            bonus = int(bonus)
            break
        else:
            print("Invalid! Enter number 1-49.")
    
    # Create new row
    new_row = {
        'Date': date,
        'Num1': numbers[0],
        'Num2': numbers[1],
        'Num3': numbers[2],
        'Num4': numbers[3],
        'Num5': numbers[4],
        'Num6': numbers[5],
        'Bonus': bonus
    }
    
    # Add to dataset
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv('lotto_649_complete.csv', index=False)
    
    print(f"\n✅ Added new draw: {date}")
    print(f"🔢 Numbers: {numbers}")
    print(f"🎯 Bonus: {bonus}")

if __name__ == "__main__":
    add_new_draw()