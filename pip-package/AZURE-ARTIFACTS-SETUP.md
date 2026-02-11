# Azure Artifacts Feed Setup Guide

## Step 1: Create the Feed

1. Go to Azure DevOps: https://dev.azure.com/msazure/One
2. Click **Artifacts** in left sidebar
3. Click **+ Create Feed**
4. Configure:
   - **Name**: `FabricLiveTable`
   - **Visibility**: `Members of msazure` (or your org)
   - **Scope**: `Organization` (so all projects can access)
   - Check: `Include packages from common public sources`
5. Click **Create**

## Step 2: Get Connection Details

After creating the feed:
1. Click on your new feed `FabricLiveTable`
2. Click **Connect to feed**
3. Select **Python** → **pip**
4. You'll see your feed URL like:
   ```
   https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
   ```

## Step 3: Create Personal Access Token (PAT)

1. Click your profile icon (top right) → **Personal access tokens**
2. Click **+ New Token**
3. Configure:
   - **Name**: `FabricLiveTable-PyPI`
   - **Expiration**: 1 year (or your preference)
   - **Scopes**: Select **Packaging** → **Read & write**
4. Click **Create**
5. **COPY THE TOKEN** - you won't see it again!

## Step 4: Configure twine for Publishing

Create/edit `~/.pypirc`:
```ini
[distutils]
index-servers =
    fabriclivetable

[fabriclivetable]
repository = https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/upload/
username = anything
password = YOUR_PAT_TOKEN_HERE
```

## Step 5: Publish the Package

```bash
cd tools/flt-edog-devmode-pip
pip install twine
twine upload --repository fabriclivetable dist/*
```

## Step 6: Share with Team

Tell teammates to run:
```bash
pip install flt-edog-devmode --index-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
```

Or they can add to their pip.conf for permanent access:
```ini
# Windows: %APPDATA%\pip\pip.ini
# Linux/Mac: ~/.config/pip/pip.conf

[global]
extra-index-url = https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/simple/
```

Then just: `pip install flt-edog-devmode`

---

## Alternative: Use Azure CLI (Automated)

If you have Azure CLI installed:

```bash
# Login
az login

# Create feed (if you have permissions)
az artifacts feed create --name FabricLiveTable --org https://dev.azure.com/msazure --project One

# Publish using artifacts-keyring (auto-auth)
pip install artifacts-keyring twine
twine upload --repository-url https://pkgs.dev.azure.com/msazure/_packaging/FabricLiveTable/pypi/upload/ dist/*
```

The `artifacts-keyring` package handles authentication automatically using your Azure credentials.
