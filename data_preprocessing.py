# -*- coding: utf-8 -*-
!pip install fastai

#  Mount Drive and Import Libraries in colab
from google.colab import drive
drive.mount('/content/drive')

import numpy as np
import pandas as pd
import os
from pathlib import Path
from fastai.tabular.all import df_shrink
from fastcore.parallel import parallel


# Column naming consistency dictionary for CIC Datasets since some naming issues
col_name_consistency = {
    'Flow Duration': 'Flow Duration',
    'Total Fwd Packets': 'Total Fwd Packets',
    'Total Backward Packets': 'Total Backward Packets',
    'Fwd Packets Length Total': 'Fwd Packets Length Total',
    'Bwd Packets Length Total': 'Bwd Packets Length Total',
}

# Columns to drop (metadata that shouldn't be used , found from other notebooks working on CIC datasets)
drop_columns = [
    "Flow ID",
    'Fwd Header Length.1',
    "Source IP", "Src IP",
    "Source Port", "Src Port",
    "Destination IP", "Dst IP",
    "Destination Port", "Dst Port",
    "Timestamp",
]

# File mapping for output names (corrected Thuesday spelling to Thursday as well)
file_mapping = {
    'Friday-02-03-2018_TrafficForML_CICFlowMeter.csv': 'Botnet-Friday-02-03-2018_TrafficForML_CICFlowMeter.parquet',
    'Friday-16-02-2018_TrafficForML_CICFlowMeter.csv': 'DoS2-Friday-16-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Friday-23-02-2018_TrafficForML_CICFlowMeter.csv': 'Web2-Friday-23-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Thursday-15-02-2018_TrafficForML_CICFlowMeter.csv': 'DoS1-Thursday-15-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Thursday-22-02-2018_TrafficForML_CICFlowMeter.csv': 'Web1-Thursday-22-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Thuesday-20-02-2018_TrafficForML_CICFlowMeter.csv': 'DDoS1-Tuesday-20-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv': 'Bruteforce-Wednesday-14-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Wednesday-21-02-2018_TrafficForML_CICFlowMeter.csv': 'DDoS2-Wednesday-21-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Wednesday-28-02-2018_TrafficForML_CICFlowMeter.csv': 'Infil1-Wednesday-28-02-2018_TrafficForML_CICFlowMeter.parquet',
    'Thursday-01-03-2018_TrafficForML_CICFlowMeter.csv': 'Infil2-Thursday-01-03-2018_TrafficForML_CICFlowMeter.parquet'
}

# Load and process data
input_dir = '/content/drive/MyDrive/CSE-CIC-IDS2018-Raw' #change this to original download dataset
csv_files = list(Path(input_dir).glob('*.csv'))
file_paths = [str(f) for f in csv_files]

print(f"Found {len(file_paths)} CSV files")
for f in file_paths:
    print(f"  {Path(f).name}")



individual_dfs = [pd.read_csv(fp, sep=',', encoding='utf-8', low_memory=False) for fp in file_paths]
print(f"Initial shapes: {[df.shape for df in individual_dfs]}")


for df in individual_dfs:
    df.columns = df.columns.str.strip()
    df.drop(columns=drop_columns, inplace=True, errors='ignore')
    df.rename(columns=col_name_consistency, inplace=True)
    df['Label'] = df['Label'].replace({'BENIGN': 'Benign'})

print(f"After column cleaning: {[df.shape for df in individual_dfs]}")



for df in individual_dfs:
    # Convert Protocol column to numeric, handling any string values
    if 'Protocol' in df.columns:
        df['Protocol'] = pd.to_numeric(df['Protocol'], errors='coerce')

    # Convert all numeric columns, handling any string values
    for col in df.columns:
        if col != 'Label':
            df[col] = pd.to_numeric(df[col], errors='coerce')



individual_dfs = parallel(f=df_shrink, items=individual_dfs, progress=True)


print("Remove NaN values")
for df in individual_dfs:
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    nan_count = df.isna().any(axis=1).sum()
    print(f"{nan_count} rows with at least one NaN to remove")
    df.dropna(inplace=True)

print(f"After NaN removal: {[df.shape for df in individual_dfs]}")


print("Remove duplicates")
for df in individual_dfs:
    dup_count = df.duplicated().sum()
    print(f"{dup_count} fully duplicate rows to remove")
    df.drop_duplicates(inplace=True)
    df.reset_index(inplace=True, drop=True)

print(f"Final shapes: {[df.shape for df in individual_dfs]}")

output_dir = '/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned' #change output if needed
os.makedirs(output_dir, exist_ok=True)

print("Saving parquet files to Google Drive...")
for i, df in enumerate(individual_dfs):
    input_filename = Path(file_paths[i]).name
    output_filename = file_mapping.get(input_filename, f"{Path(file_paths[i]).stem}.parquet")
    output_path = Path(output_dir) / output_filename

    df.to_parquet(output_path)
    print(f"Saved: {output_filename}")

print(f"Files saved to: {output_dir}")

# final statistics
total_records = sum(df.shape[0] for df in individual_dfs)
print(f"Total cleaned records: {total_records:,}")
print(f"Features per record: {individual_dfs[0].shape[1]}")
print(f"Files created: {len(individual_dfs)}")
