import sys

import pandas as pd

df = pd.DataFrame({"day": [1, 2], "number_passengers": [3, 4]})
month = int(sys.argv[1])
df["month"] = month

df.to_parquet(f"output_{month}.parquet")

print(df.head())
print(f"hello world, month={month}")