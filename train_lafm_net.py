# -*- coding: utf-8 -*-
"""
LAFM-Net Adaptive Feature Masking Network on the CIC-IDS-2018 dataset

- Multichannel representation of tabular flow data
- Simplified U-Net for feature enhancement
- Learnable adaptive feature masking
- 1D CNN classifier
- Focal loss for imbalance handling
- Early stopping + validation tracking
"""
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
from sklearn.decomposition import PCA
import torchvision.transforms.functional as TF
import random
import matplotlib.pyplot as plt
import seaborn as sns
import time
import os
import pickle
import copy
import gc

class LearnableAdaptiveMasking(nn.Module):
    def __init__(self, channels, image_size):
        super().__init__()
        # per channel temperature and bias
        self.temperature = nn.Parameter(torch.ones(1))
        self.bias = nn.Parameter(torch.zeros(channels))
        # channel‐wise learnable scaling
        self.channel_scale = nn.Parameter(torch.ones(channels, 1, 1))
        # global importance gating
        self.global_fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(channels, channels),
            nn.Sigmoid()
        )

    def forward(self, x):
        # x: B x C x H x W
        scaled = (x * self.channel_scale + self.bias.view(1, -1, 1, 1)) / self.temperature
        base_mask = torch.sigmoid(scaled)
        g = self.global_fc(x).view(-1, x.size(1), 1, 1)
        return base_mask * g

CONFIG = {
    "parquet_file_paths": [
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Bruteforce-Wednesday-14-02-2018_TrafficForML_CICFlowMeter.parquet",
     "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Infil1-Wednesday-28-02-2018_TrafficForML_CICFlowMeter.parquet",
     "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/DDoS2-Wednesday-21-02-2018_TrafficForML_CICFlowMeter.parquet",
      "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Botnet-Friday-02-03-2018_TrafficForML_CICFlowMeter.parquet",
      "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/DoS2-Friday-16-02-2018_TrafficForML_CICFlowMeter.parquet",
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Web2-Friday-23-02-2018_TrafficForML_CICFlowMeter.parquet",
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/DDoS1-Tuesday-20-02-2018_TrafficForML_CICFlowMeter.parquet",
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/DoS1-Thursday-15-02-2018_TrafficForML_CICFlowMeter.parquet",
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Infil2-Thursday-01-03-2018_TrafficForML_CICFlowMeter.parquet",
    "/content/drive/MyDrive/CSE-CIC-IDS2018-Cleaned/Web1-Thursday-22-02-2018_TrafficForML_CICFlowMeter.parquet"
    ],
    "target_column": "Label",
    "num_features_per_channel": 16,
    "image_size": 4,
    "num_channels": 4,
    "total_features": 64,
    "correlation_threshold": 0.999,
    "batch_size": 256,
    "unet_lr": 1e-4,
    "classifier_lr": 2e-4,
    "unet_epochs": 30,
    "classifier_epochs": 30,
    "masking_ts_range": (5, 15),
    "early_stopping_patience": 5,
    "noise_factor_unet_train": 0.1,
    "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
    "random_seed": 123,
    "test_set_ratio": 0.25,
    "validation_set_ratio": 0.20,
    "augmentation_flip_prob": 0.3,
    "minority_class_threshold": 0.01,
    "focal_loss_alpha": 0.75,
    "focal_loss_gamma": 1.5,
}

# instantiate the adaptive masker
adaptive_masker = LearnableAdaptiveMasking(
    channels=CONFIG["num_channels"],
    image_size=CONFIG["image_size"]
).to(CONFIG["device"])

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

set_seed(CONFIG["random_seed"])

print(f"LAFM-Net on CIC-IDS-2018 dataset: Enhanced Feature Masking Network with Multichannel Support, Validation, and Early Stopping")
print(f"Using device: {CONFIG['device']}")
print(f"Image configuration: {CONFIG['num_channels']} channels, {CONFIG['image_size']}x{CONFIG['image_size']} per channel")

CONFIG["num_classes"] = 0

def consolidate_labels(labels):
    """
    0: Benign
    1: DoS (any DoS attack)
    2: DDoS (any DDoS attack)
    3: Botnet (Bot)
    4: Infiltration
    5: Brute Force (any brute force attack)
    """
    consolidated = []

    for label in labels:
        label_lower = str(label).lower()

        if 'benign' in label_lower:
            consolidated.append('Benign')
        elif 'ddos' in label_lower:
            consolidated.append('DDoS')
        elif 'dos' in label_lower:
            consolidated.append('DoS')
        elif 'bot' in label_lower:
            consolidated.append('Botnet')
        elif 'infil' in label_lower:
            consolidated.append('Infiltration')
        elif any(x in label_lower for x in ['brute', 'bruteforce', 'ssh', 'ftp', 'web', 'xss', 'sql']):
            consolidated.append('Brute Force')
        else:
            # default mapping for unknown categories (doesn't matter here)
            consolidated.append('Brute Force')

    return consolidated

class EarlyStopping:
    def __init__(self, patience=7, verbose=False, delta=0, path='checkpoint.pt', trace_func=print):
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = np.inf
        self.delta = delta
        self.path = path
        self.trace_func = trace_func
        self.best_model_state_dict = None

    def __call__(self, val_loss, model):
        score = -val_loss
        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
        elif score < self.best_score + self.delta:
            self.counter += 1
            if self.verbose:
                self.trace_func(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
            self.counter = 0

    def save_checkpoint(self, val_loss, model):
        if self.verbose:
            self.trace_func(f'Validation loss decreased ({self.val_loss_min:.6f} --> {val_loss:.6f}).  Saving model ...')
        self.best_model_state_dict = copy.deepcopy(model.state_dict())
        self.val_loss_min = val_loss

    def load_best_weights(self, model):
        if self.best_model_state_dict is not None:
            model.load_state_dict(self.best_model_state_dict)
            if self.verbose:
                self.trace_func("Loaded best model weights from early stopping.")
        else:
            if self.verbose:
                self.trace_func("No best model weights to load from early stopping.")

def correlation_filtering(df, threshold):
    print(f"\nApplying correlation filtering with threshold {threshold}...")
    numeric_df = df.select_dtypes(include=np.number)
    if numeric_df.shape[1] < 2:
        print("Not enough numeric columns for correlation filtering.")
        return df

    corr_matrix = numeric_df.corr().abs()
    upper_tri = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    drop_cols = [column for column in upper_tri.columns if any(upper_tri[column] > threshold)]

    if drop_cols:
        print(f"Dropping {len(drop_cols)} highly correlated features: {drop_cols}")
        df_filtered = df.drop(columns=drop_cols)
    else:
        print("No features dropped by correlation filtering.")
        df_filtered = df
    return df_filtered

def load_and_prepare_data_from_parquets(parquet_paths, target_column_name):
    individual_dfs = []
    print("Loading parquet files...")

    for p_path in parquet_paths:
        if os.path.exists(p_path):
            try:
                df_temp = pd.read_parquet(p_path)
                individual_dfs.append(df_temp)
                print(f"Loaded {os.path.basename(p_path)}: {df_temp.shape}")
            except Exception as e:
                print(f"Error loading {p_path}: {e}")
        else:
            print(f"File not found: {p_path}")

    if not individual_dfs:
        print("No dataframes loaded.")
        return None, None

    print("Concatenating DataFrames...")
    df_data = pd.concat(individual_dfs, axis=0, ignore_index=True)
    print(f"Combined shape: {df_data.shape}")

    initial_rows = len(df_data)
    df_data.replace([np.inf, -np.inf], np.nan, inplace=True)
    df_data.dropna(inplace=True)
    print(f"Dropped {initial_rows - len(df_data)} rows with NaN/inf")

    initial_rows = len(df_data)
    df_data.drop_duplicates(inplace=True)
    print(f"Dropped {initial_rows - len(df_data)} duplicate rows")

    df_data.reset_index(drop=True, inplace=True)
    print(f"Final shape: {df_data.shape}")

    if target_column_name not in df_data.columns:
        print(f"ERROR: Target '{target_column_name}' not found.")
        return None, None

    print("Original class distribution:")
    print(df_data[target_column_name].value_counts().head(15))

    # consolidate labels
    print("\nConsolidating labels into 6 main categories...")
    df_data[target_column_name] = consolidate_labels(df_data[target_column_name])

    print("\nConsolidated class distribution:")
    print(df_data[target_column_name].value_counts())

    X = df_data.drop(columns=[target_column_name])
    y_str = df_data[target_column_name]
    return X, y_str

def process_features_multichannel(X_df, y_series, total_features, correlation_thresh, random_seed):
    print(f"\nProcessing features for multichannel representation ({total_features} total features)...")

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y_series)
    num_classes = len(label_encoder.classes_)
    CONFIG["num_classes"] = num_classes
    print(f"Target encoded. Classes: {num_classes}")
    print(f"Class mapping: {dict(zip(label_encoder.classes_, label_encoder.transform(label_encoder.classes_)))}")

    X_numerical_df = X_df.select_dtypes(include=np.number).copy()
    if X_numerical_df.empty:
        print("ERROR: No numeric features.")
        return None, None, None, None

    X_corr_filtered = correlation_filtering(X_numerical_df, correlation_thresh)
    print(f"Features after correlation filtering: {X_corr_filtered.shape[1]}")

    scaler = StandardScaler()
    X_scaled_array = scaler.fit_transform(X_corr_filtered)
    print(f"Features scaled: {X_scaled_array.shape}")

    actual_components = min(total_features, X_scaled_array.shape[1], X_scaled_array.shape[0])
    if actual_components <= 0:
        print(f"ERROR: Not enough samples or features for PCA ({X_scaled_array.shape[0]} samples, {X_scaled_array.shape[1]} features).")
        return None, None, None, None

    pca = PCA(n_components=actual_components, random_state=random_seed)
    try:
        X_pca_array = pca.fit_transform(X_scaled_array)
        print(f"PCA applied: {X_pca_array.shape}, explained variance: {np.sum(pca.explained_variance_ratio_):.4f}")
    except ValueError as e:
        print(f"Error during PCA: {e}.")
        return None, None, None, None

    if X_pca_array.shape[1] < total_features:
        padding = np.zeros((X_pca_array.shape[0], total_features - X_pca_array.shape[1]))
        X_final_features = np.hstack((X_pca_array, padding))
    else:
        X_final_features = X_pca_array[:, :total_features]

    print(f"Final feature array: {X_final_features.shape}")
    return X_final_features, y_encoded, label_encoder, scaler, pca

def features_to_multichannel_image(feature_vector, num_channels, features_per_channel, image_size):
    channels = []
    for c in range(num_channels):
        start_idx = c * features_per_channel
        end_idx = start_idx + features_per_channel
        if end_idx <= len(feature_vector):
            channel_features = feature_vector[start_idx:end_idx]
        else:
            available = len(feature_vector) - start_idx
            if available > 0:
                channel_features = np.concatenate([
                    feature_vector[start_idx:],
                    np.zeros(features_per_channel - available)
                ])
            else:
                channel_features = np.zeros(features_per_channel)
        channels.append(channel_features.reshape((image_size, image_size)))
    return np.stack(channels, axis=0)

class MultichannelFlowDataset(Dataset):
    def __init__(self, feature_array, label_array, num_channels, features_per_channel, image_size,
                 augment=False, minority_classes=None, flip_prob=0.3):
        self.labels = label_array
        self.augment = augment
        self.flip_prob = flip_prob
        self.minority_classes = minority_classes or []

        print(f"Converting {len(feature_array)} samples to multichannel images for {'augmented' if augment else 'standard'} dataset...")
        self.images = []
        for i, feats in enumerate(feature_array):
            img = features_to_multichannel_image(feats, num_channels, features_per_channel, image_size)
            self.images.append(torch.tensor(img, dtype=torch.float32))
            if (i + 1) % 100000 == 0 or (i+1) == len(feature_array):  # Less frequent progress updates
                print(f"Processed {i + 1}/{len(feature_array)} samples.")
                gc.collect()  # Simple memory cleanup
        print(f"Dataset created: {len(self.images)} samples.")
        if self.augment and self.minority_classes:
            print(f"Augmentation enabled for {len(self.minority_classes)} minority classes.")

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        img = self.images[idx].clone()
        lbl = torch.tensor(self.labels[idx], dtype=torch.long)
        if self.augment and lbl.item() in self.minority_classes:
            if random.random() < self.flip_prob:
                img = TF.hflip(img)
            if random.random() < self.flip_prob:
                img = TF.vflip(img)
        return img, lbl

class SimpleMaskingUNet(nn.Module):
    def __init__(self, in_channels=4, out_channels=4, base_features=32):
        super().__init__()
        self.enc1 = self._make_block(in_channels, base_features)
        self.enc2 = self._make_block(base_features, base_features*2)
        self.bottleneck = self._make_block(base_features*2, base_features*4)
        self.up2 = nn.ConvTranspose2d(base_features*4, base_features*2, 2, stride=2)
        self.dec2 = self._make_block(base_features*4, base_features*2)
        self.up1 = nn.ConvTranspose2d(base_features*2, base_features, 2, stride=2)
        self.dec1 = self._make_block(base_features*2, base_features)
        self.final = nn.Conv2d(base_features, out_channels, 1)

    def _make_block(self, in_c, out_c):
        return nn.Sequential(
            nn.Conv2d(in_c, out_c, 3, padding=1), nn.BatchNorm2d(out_c), nn.ReLU(inplace=True),
            nn.Conv2d(out_c, out_c, 3, padding=1), nn.BatchNorm2d(out_c), nn.ReLU(inplace=True)
        )

    def forward(self, x):
        e1 = self.enc1(x)
        p1 = F.max_pool2d(e1, 2)
        e2 = self.enc2(p1)
        p2 = F.max_pool2d(e2, 2)
        b = self.bottleneck(p2)
        u2 = self.up2(b)
        d2 = self.dec2(torch.cat([u2, e2], dim=1))
        u1 = self.up1(d2)
        d1 = self.dec1(torch.cat([u1, e1], dim=1))
        return self.final(d1)

def feature_masking_enhancement(original_imgs, frozen_unet, ts_range, device):
    frozen_unet.eval()
    adaptive_masker.eval()
    with torch.no_grad():
        feats = frozen_unet(original_imgs)
        mask = adaptive_masker(feats)
        enhanced = original_imgs * mask
        return torch.clamp(enhanced, 0.0, 1.0)

class Lightweight1DClassifier(nn.Module):
    def __init__(self, input_channels=4, input_size=4, num_classes=6, dropout_rate1=0.3, dropout_rate2=0.2):  # Changed default to 6
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1,64,5,padding=2), nn.ReLU(), nn.BatchNorm1d(64), nn.MaxPool1d(2),
            nn.Conv1d(64,128,3,padding=1), nn.ReLU(), nn.BatchNorm1d(128), nn.MaxPool1d(2),
            nn.Conv1d(128,256,3,padding=1), nn.ReLU(), nn.BatchNorm1d(256), nn.AdaptiveMaxPool1d(8)
        )
        self.fc = nn.Sequential(
            nn.Dropout(dropout_rate1), nn.Linear(256*8,512), nn.ReLU(),
            nn.Dropout(dropout_rate2), nn.Linear(512,128), nn.ReLU(),
            nn.Linear(128,num_classes)
        )

    def forward(self, x):
        b = x.size(0)
        flat = x.view(b,1,-1)
        c = self.conv(flat)
        return self.fc(c.view(b,-1))

class BalancedFocalLoss(nn.Module):
    def __init__(self, alpha=0.75, gamma=1.5, device='cuda'):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.device = device

    def forward(self, inputs, targets):
        ce = F.cross_entropy(inputs, targets, reduction='none')
        pt = torch.exp(-ce)
        alpha_t = torch.full_like(targets, self.alpha, device=self.device, dtype=torch.float32)
        return (alpha_t * (1 - pt)**self.gamma * ce).mean()

def train_masking_unet(unet, train_loader, val_loader, config):
    print("Training U-Net for feature masking...")
    unet.to(config["device"])
    opt = optim.Adam(unet.parameters(), lr=config["unet_lr"])
    crit = nn.MSELoss()
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, 'min', patience=config["early_stopping_patience"]//2, factor=0.1, verbose=True)
    stopper = EarlyStopping(patience=config["early_stopping_patience"], verbose=True, path='unet_checkpoint.pt')
    history = {'train_loss':[], 'val_loss':[]}

    for ep in range(config["unet_epochs"]):
        unet.train()
        t_loss = 0.0
        for batch_idx, (imgs, _) in enumerate(train_loader):
            imgs = imgs.to(config["device"])
            opt.zero_grad()
            noisy = imgs + torch.randn_like(imgs)*config["noise_factor_unet_train"]
            recon = unet(noisy)
            loss = crit(recon, imgs)
            loss.backward()
            opt.step()
            t_loss += loss.item()

            if batch_idx % 500 == 0:
                gc.collect()

        history['train_loss'].append(t_loss/len(train_loader))

        unet.eval()
        v_loss = 0.0
        with torch.no_grad():
            for imgs, _ in val_loader:
                imgs = imgs.to(config["device"])
                noisy = imgs + torch.randn_like(imgs)*config["noise_factor_unet_train"]
                recon = unet(noisy)
                v_loss += crit(recon, imgs).item()
        v_avg = v_loss/len(val_loader)
        history['val_loss'].append(v_avg)
        print(f"Epoch {ep+1}: Train {history['train_loss'][-1]:.6f}, Val {v_avg:.6f}")
        sched.step(v_avg)
        stopper(v_avg, unet)
        if stopper.early_stop:
            print("Early stopping U-Net.")
            break

    stopper.load_best_weights(unet)
    return unet, history

def train_classifier_end_to_end(classifier, frozen_unet, train_loader, val_loader, config):
    print("Training classifier end-to-end...")
    classifier.to(config["device"])
    frozen_unet.to(config["device"]).eval()

    # adaptive_masker parameters
    opt = optim.Adam(
        list(classifier.parameters()) + list(adaptive_masker.parameters()),
        lr=config["classifier_lr"]
    )
    crit = BalancedFocalLoss(alpha=config["focal_loss_alpha"], gamma=config["focal_loss_gamma"], device=config["device"])
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, 'min', patience=config["early_stopping_patience"]//2, factor=0.1, verbose=True)
    stopper = EarlyStopping(patience=config["early_stopping_patience"], verbose=True, path='classifier_checkpoint.pt')

    history = {'train_loss':[], 'train_acc':[], 'val_loss':[], 'val_acc':[], 'val_f1':[]}

    for ep in range(config["classifier_epochs"]):
        classifier.train()
        t_loss, correct, total = 0.0, 0, 0
        for batch_idx, (imgs, labels) in enumerate(train_loader):
            imgs, labels = imgs.to(config["device"]), labels.to(config["device"])
            opt.zero_grad()
            enh = feature_masking_enhancement(imgs, frozen_unet, config["masking_ts_range"], config["device"])
            preds = classifier(enh)
            loss = crit(preds, labels)
            loss.backward()
            opt.step()
            t_loss += loss.item()
            _, p_lbl = preds.max(1)
            correct += (p_lbl==labels).sum().item()
            total += labels.size(0)

            if batch_idx % 500 == 0:
                gc.collect()

        history['train_loss'].append(t_loss/len(train_loader))
        history['train_acc'].append(correct/total)

        classifier.eval()
        v_loss, v_corr, v_tot = 0.0,0,0
        all_t, all_p = [], []
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(config["device"]), labels.to(config["device"])
                enh = feature_masking_enhancement(imgs, frozen_unet, config["masking_ts_range"], config["device"])
                preds = classifier(enh)
                loss = crit(preds, labels)
                v_loss += loss.item()
                _, p_lbl = preds.max(1)
                v_corr += (p_lbl==labels).sum().item()
                v_tot += labels.size(0)
                all_t.extend(labels.cpu().numpy())
                all_p.extend(p_lbl.cpu().numpy())
        v_avg = v_loss/len(val_loader)
        acc = v_corr/v_tot
        f1 = f1_score(all_t, all_p, average='weighted', zero_division=0)
        history['val_loss'].append(v_avg)
        history['val_acc'].append(acc)
        history['val_f1'].append(f1)
        print(f"Epoch {ep+1}: Train L {history['train_loss'][-1]:.6f}, A {history['train_acc'][-1]:.4f} | Val L {v_avg:.6f}, A {acc:.4f}, F1 {f1:.4f}")
        sched.step(v_avg)
        stopper(v_avg, classifier)
        if stopper.early_stop:
            print("Early stopping classifier.")
            break

    stopper.load_best_weights(classifier)
    return classifier, history

def evaluate_model(classifier, frozen_unet, test_loader, config, label_encoder, set_name="Test"):
    print(f"\nEvaluating model on {set_name} set...")
    classifier.eval()
    frozen_unet.eval()
    all_pred, all_true = [], []

    with torch.no_grad():
        for batch_idx, (imgs, labels) in enumerate(test_loader):
            imgs, labels = imgs.to(config["device"]), labels.to(config["device"])
            enh = feature_masking_enhancement(imgs, frozen_unet, config["masking_ts_range"], config["device"])
            outs = classifier(enh)
            _, p_lbl = outs.max(1)
            all_pred.extend(p_lbl.cpu().numpy())
            all_true.extend(labels.cpu().numpy())

            if batch_idx % 100 == 0:
                gc.collect()

    names = label_encoder.classes_
    print(classification_report(all_true, all_pred, target_names=names, digits=4, zero_division=0))
    cm = confusion_matrix(all_true, all_pred, labels=label_encoder.transform(names))
    plt.figure(figsize=(max(10,len(names)*0.8),max(8,len(names)*0.6)))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=names, yticklabels=names)
    plt.title(f'Confusion Matrix')
    plt.xlabel('Predicted'); plt.ylabel('Actual')
    plt.tight_layout(); plt.show()

    if 'Benign' in names:
        b_enc = label_encoder.transform(['Benign'])[0]
        y_t = np.where(np.array(all_true)==b_enc,0,1)
        y_p = np.where(np.array(all_pred)==b_enc,0,1)
        print("\nBinary (Benign vs Attack):")
        print(classification_report(y_t, y_p, target_names=['Benign','Attack'], digits=4, zero_division=0))
        cm_bin = confusion_matrix(y_t, y_p, labels=[0,1])
        plt.figure(figsize=(5,4))
        sns.heatmap(cm_bin, annot=True, fmt='d', cmap='Blues',
                   xticklabels=['Benign','Attack'],
                   yticklabels=['Benign','Attack'])
        plt.title('Binary Confusion Matrix – Benign vs Attack')
        plt.xlabel('Predicted')
        plt.ylabel('Actual')
        plt.tight_layout()
        plt.show()
    return all_true, all_pred

def plot_training_curves_generic(data_list, label_list, title="Training Curves"):
    plt.figure(figsize=(8,5))
    for d,l in zip(data_list,label_list):
        if d: plt.plot(d,label=l)
    plt.title(title); plt.xlabel('Epoch'); plt.ylabel('Value')
    plt.legend(); plt.grid(True); plt.tight_layout(); plt.show()

def main_training_and_evaluation(current_config):
    set_seed(current_config["random_seed"])
    X_raw, y_raw = load_and_prepare_data_from_parquets(current_config["parquet_file_paths"], current_config["target_column"])
    if X_raw is None: return
    X_feats, y_enc, lbl_enc, scl, pca = process_features_multichannel(X_raw, y_raw,
        current_config["total_features"], current_config["correlation_threshold"], current_config["random_seed"])
    if X_feats is None: return

    current_config["num_classes"] = len(lbl_enc.classes_)
    X_trval, X_test, y_trval, y_test = train_test_split(X_feats, y_enc, test_size=current_config["test_set_ratio"],
                                                        random_state=current_config["random_seed"], stratify=y_enc)
    X_train, X_val, y_train, y_val = train_test_split(
        X_trval, y_trval, test_size=current_config["validation_set_ratio"],
        random_state=current_config["random_seed"], stratify=y_trval)

    del X_feats, y_enc, X_trval, y_trval
    gc.collect()

    train_ds = MultichannelFlowDataset(X_train, y_train, current_config["num_channels"],
        current_config["num_features_per_channel"], current_config["image_size"], augment=True,
        minority_classes=pd.Series(y_train).value_counts(normalize=True)[lambda x:x<current_config["minority_class_threshold"]].index.tolist(),
        flip_prob=current_config["augmentation_flip_prob"])
    val_ds = MultichannelFlowDataset(X_val, y_val, current_config["num_channels"],
        current_config["num_features_per_channel"], current_config["image_size"])
    test_ds = MultichannelFlowDataset(X_test, y_test, current_config["num_channels"],
        current_config["num_features_per_channel"], current_config["image_size"])


    bs = min(current_config["batch_size"], len(train_ds), len(val_ds)) or 1
    train_ld = DataLoader(train_ds, batch_size=bs, shuffle=True, num_workers=2, pin_memory=True, drop_last=True)
    val_ld   = DataLoader(val_ds,   batch_size=bs, shuffle=False, num_workers=2, pin_memory=True)
    test_ld  = DataLoader(test_ds,  batch_size=bs, shuffle=False, num_workers=2, pin_memory=True)

    print("Initializing models...")
    unet = SimpleMaskingUNet(in_channels=current_config["num_channels"],
                             out_channels=current_config["num_channels"], base_features=32).to(CONFIG["device"])
    clf  = Lightweight1DClassifier(input_channels=current_config["num_channels"],
                                   input_size=current_config["image_size"],
                                   num_classes=current_config["num_classes"])


    unet, unet_hist = train_masking_unet(unet, train_ld, val_ld, current_config)
    for p in unet.parameters(): p.requires_grad=False
    plot_training_curves_generic([unet_hist['train_loss'], unet_hist['val_loss']], ['Train Loss','Val Loss'], "U-Net Loss")

    clf, clf_hist = train_classifier_end_to_end(clf, unet, train_ld, val_ld, current_config)

    print("\nFully trained LAFM-Net: All 4 channels before and after masking")
    batch_imgs, batch_lbls = next(iter(train_ld))
    batch_imgs = batch_imgs.to(CONFIG["device"])
    enh_imgs = feature_masking_enhancement(batch_imgs, unet, CONFIG["masking_ts_range"], CONFIG["device"])

    # Show first sample, all 4 channels
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))

    for ch in range(4):
        im1 = axes[0, ch].imshow(batch_imgs[0, ch].cpu().numpy(), cmap='viridis')
        axes[0, ch].set_title(f"Original Ch {ch}")
        axes[0, ch].axis('off')
        plt.colorbar(im1, ax=axes[0, ch], fraction=0.046)

    for ch in range(4):
        im2 = axes[1, ch].imshow(enh_imgs[0, ch].cpu().numpy(), cmap='viridis')
        axes[1, ch].set_title(f"Enhanced Ch {ch}")
        axes[1, ch].axis('off')
        plt.colorbar(im2, ax=axes[1, ch], fraction=0.046)

    plt.suptitle(f"LAFM-Net: Original vs Enhanced Features (Sample 0, Label {batch_lbls[0].item()})")
    plt.tight_layout()
    plt.show()

    plot_training_curves_generic([clf_hist['train_loss'], clf_hist['val_loss']], ['Train Loss','Val Loss'], "Classifier Loss")
    plot_training_curves_generic([clf_hist['train_acc'], clf_hist['val_acc'], clf_hist['val_f1']],
                                 ['Train Acc','Val Acc','Val F1'], "Classifier Performance")

    print("\nFinal Evaluation on Test Set")
    true_t, pred_t = evaluate_model(clf, unet, test_ld, current_config, lbl_enc, set_name="Test")
    print(f"Test Accuracy: {accuracy_score(true_t,pred_t):.4f}, Weighted F1: {f1_score(true_t,pred_t,average='weighted',zero_division=0):.4f}")

    # Save models
    torch.save(unet.state_dict(), 'lafm_net_18_unet_multichannel_final.pth')
    torch.save(clf.state_dict(), 'lafm_net_18_classifier_multichannel_final.pth')
    torch.save(adaptive_masker.state_dict(), 'lafm_net_18_adaptive_masker_final.pth')
    with open('lafm_net_18_label_encoder_final.pkl','wb') as f: pickle.dump(lbl_enc, f)
    with open('lafm_net_18_scaler_final.pkl','wb') as f: pickle.dump(scl, f)
    with open('lafm_net_18_pca_final.pkl','wb') as f: pickle.dump(pca, f)

    print("\nSaved files:")
    print("- lafm_net_18_unet_multichannel_final.pth")
    print("- lafm_net_18_classifier_multichannel_final.pth")
    print("- lafm_net_18_adaptive_masker_final.pth")
    print("- lafm_net_18_label_encoder_final.pkl")
    print("- lafm_net_18_scaler_final.pkl")
    print("- lafm_net_18_pca_final.pkl")

if __name__ == '__main__':
    main_training_and_evaluation(CONFIG)
