# ⚠️ Authenticate GitHub CLI First!

You're seeing this error because GitHub CLI is not authenticated.

## Quick Fix

Run this command in PowerShell:

```powershell
gh auth login
```

## Step-by-Step Authentication

1. **Run the command:**
   ```powershell
   gh auth login
   ```

2. **Follow the prompts:**
   - **What account do you want to log into?** → Choose `GitHub.com`
   - **What is your preferred protocol?** → Choose `HTTPS`
   - **How would you like to authenticate?** → Choose `Login with a web browser`
   - Press `Enter`

3. **Browser opens:**
   - Copy the one-time code shown in terminal
   - Paste it in the browser
   - Click "Authorize"
   - Return to terminal

4. **Verify it worked:**
   ```powershell
   gh auth status
   ```
   Should show: `✓ Logged in to github.com as [your-username]`

## Then Try Again

After authenticating, run your original command:

```powershell
gh release create v0.1.0 --title "v0.1.0 - Warn-First Release" --notes-file RELEASE_NOTES.md
```

---

**Once authenticated, you can run all the setup commands!**
