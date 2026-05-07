#Set up. Summary:

Venv: costco_gas/.venv/ with curl_cffi installed (added .venv to .gitignore)
Wrapper: costco_gas/run_local.sh — pulls latest, runs the fetcher, stages pwa/data + zip_cache.json, commits + pushes only if changed. Logs to ~/Library/Logs/costco_gas.log.
Schedule: ~/Library/LaunchAgents/com.user.costco-gas.plist — fires daily at 12:00 local. Loaded.
Test it before noon (runs the same job on demand):

launchctl start com.user.costco-gas
tail -f ~/Library/Logs/costco_gas.log
One thing to watch — SSH push from launchd. Your remote is git@github.com:.... If your SSH key is stored in the macOS Keychain (UseKeychain yes in ~/.ssh/config and ssh-add --apple-use-keychain), git push will work. If not, the push will fail silently with the script logging an error — please run the manual test above and check the log. If it fails, easiest fix is to add to ~/.ssh/config:


Host github.com
  UseKeychain yes
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_ed25519
then ssh-add --apple-use-keychain ~/.ssh/id_ed25519 once.

To stop: launchctl unload ~/Library/LaunchAgents/com.user.costco-gas.plist.