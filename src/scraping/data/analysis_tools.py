"""
Lotto 6/49 Analysis Tools
Basic analysis functions for the historical dataset
"""

import pandas as pd
from collections import Counter

def load_dataset():
    """Load the Lotto 6/49 dataset"""
    return pd.read_csv('lotto_649_complete.csv')

def basic_statistics(df):
    """Generate basic statistics"""
    print("📊 LOTTO 6/49 BASIC STATISTICS")
    print("=" * 50)
    print(f"Total Draws: {len(df):,}")
    print(f"Date Range: {df['Date'].iloc[0]} to {df['Date'].iloc[-1]}")
    
    # Number frequency
    all_numbers = []
    for i in range(1, 7):
        all_numbers.extend(df[f'Num{i}'].tolist())
    
    freq = Counter(all_numbers)
    
    print("\n🎯 MOST FREQUENT NUMBERS:")
    for num, count in freq.most_common(10):
        percentage = (count / len(df)) * 100
        print(f"  #{num:2d}: {count:3d} times ({percentage:.1f}%)")
    
    print("\n🥶 LEAST FREQUENT NUMBERS:")
    for num, count in freq.most_common()[-10:]:
        percentage = (count / len(df)) * 100
        print(f"  #{num:2d}: {count:3d} times ({percentage:.1f}%)")
    
    return freq

if __name__ == "__main__":
    df = load_dataset()
    basic_statistics(df)