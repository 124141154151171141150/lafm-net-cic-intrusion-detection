# lafm-net-cic-intrusion-detection
# LAFM-Net: Network Intrusion Detection using CIC Cybersecurity Datasets

A deep learning approach for network intrusion detection using Learnable Adaptive Feature Masking Network. Primarily designed for CSE-CIC-IDS-2018 and CIC-DDoS-2019 datasets

## Overview

This project implements LAFM-Net (Learnable Adaptive Feature Masking Network) for cybersecurity threat detection. The model processes network flow data and can classify various types of network attacks and benign traffic.

## Supported Datasets

### CIC-IDS-2018
- **Source**: Canadian Institute for Cybersecurity at UNB.ca
- **Size**: ~7GB (10 CSV files)
- **Samples**: ~16M network flow records  
- **Features**: 80+ network flow features
- **Classes**: 7 attack types (Benign, DoS, DDoS, Botnet, Infiltration, Brute Force, Web attacks)

### CIC-DDoS-2019
- **Source**: Canadian Institute for Cybersecurity at UNB.ca  
- **Size**: ~30GB (2 folders with 17 CSV files in total)
- **Samples**: ~30M network flow records
- **Features**: 80+ network flow features 
- **Classes**: Multiple DDoS attack types (LDAP, DNS, NetBIOS, MSSQL, UDP, SYN, etc.)

## Dataset Download

###  CIC-IDS-2018
https://www.unb.ca/cic/datasets/ids-2018.html
https://registry.opendata.aws/cse-cic-ids2018/
Download the CSE-CIC-IDS-2018 Dataset using AWS CLI

```bash
!aws s3 sync --no-sign-request --region us-west-1 "s3://cse-cic-ids2018/Processed Traffic Data for ML Algorithms/" 
```

### CIC-DDoS-2019
https://www.unb.ca/cic/datasets/ddos-2019.html
Download the CIC-DDoS-2019 Dataset from the UNB site.

## Requirements

### System Requirements
- Google Colab
- Google Drive with 20GB+ free space

### Dependencies

The following packages are needed and will be automatically installed when you run the code:

```python
!pip install fastai
```

**Pre-installed in Colab:**
- torch, torchvision
- numpy, pandas, scikit-learn  
- matplotlib, seaborn

**Note**: All dependencies are handled automatically in the provided code.

## Usage (Google Colab)

1. **Open Google Colab** and create a new notebook
2. **Mount Google Drive**:
```python
from google.colab import drive
drive.mount('/content/drive')
```

3. **Download your chosen dataset**:

**For CIC-IDS-2018:**
```bash
!aws s3 sync --no-sign-request --region us-west-1 "s3://cse-cic-ids2018/Processed Traffic Data for ML Algorithms/" /content/drive/MyDrive/CSE-CIC-IDS2018-Raw/
```

**For CIC-DDoS-2019:**
https://www.unb.ca/cic/datasets/ddos-2019.html

4. **Copy and run the data preprocessing code** (`data_preprocessing.py`) first
5. **Copy and run the training code** (`train_lafm_net.py`) second

**Note**: The code is pre-configured for CIC-IDS-2018.

## Model Architecture

1. **Data Pipeline**: PCA → Multi-channel conversion (4×4×4)
2. **U-Net**: Feature reconstruction and masking
3. **Adaptive Masking**: Learnable feature enhancement
4. **Classifier**: Lightweight 1D CNN

**Supported Attack Types:**
- **CIC-IDS-2018**: Benign, DoS, DDoS, Botnet, Infiltration, Brute Force, Web attacks
- **CIC-DDoS-2019**: Benign, Various DDoS types (LDAP, DNS, NetBIOS, MSSQL, UDP, SYN, NTP, SNMP, etc.)

## Configuration

Key parameters can be modified in `train_lafm_net.py`:

```python
CONFIG = {
    "batch_size": 256,
    "unet_lr": 1e-4,
    "classifier_lr": 2e-4,
    "unet_epochs": 30,
    "classifier_epochs": 30,
    "total_features": 64,
    "num_channels": 4,
    "image_size": 4,
}
```

## Results

The model provides:
- Multi-class classification (attack type detection)
- Binary classification (Benign vs Attack)
- Performance metrics and confusion matrices
- Feature masking visualizations

**Expected Performance:**
- **CIC-IDS-2018**: Binary or multiclass classification 
- **CIC-DDoS-2019**: Binary or multiclass classification

## Files

- `data_preprocessing.py` - Data cleaning and preprocessing 
- `train_lafm_net.py` - Complete model training pipeline 
- `README.md` - Documentation

**Dataset Compatibility Notes:**
- For CIC-DDoS-2019: May need to adjust file paths and label consolidation in the scripts
- Both datasets use the same 80+ feature format from CICFlowMeter

## Hardware Recommendations

- **Google Colab Free**: Works but may have memory limitations
- **Google Colab Pro**: Recommended for faster training and more RAM
- **Runtime**: GPU runtime recommended for faster training

## Citation

If you use this code or the datasets:

**For CIC-IDS-2018:**
https://registry.opendata.aws/cse-cic-ids2018/
```
Sharafaldin, Iman, Arash Habibi Lashkari, and Ali A. Ghorbani. 
"Toward generating a new intrusion detection dataset and intrusion traffic characterization." 
4th International Conference on Information Systems Security and Privacy (ICISSP). 2018.
```

**For CIC-DDoS-2019:**
```
Sharafaldin, Iman, Arash Habibi Lashkari, Saqib Hakak, and Ali A. Ghorbani. 
"Developing realistic distributed denial of service (DDoS) attack dataset and taxonomy." 
2019 International Carnahan Conference on Security Technology (ICCST). IEEE, 2019.
```

## License

MIT License - Feel free to use and modify.

## Acknowledgments

- University of New Brunswick for the CIC-IDS-2018 and CIC-DDoS-2019 datasets
