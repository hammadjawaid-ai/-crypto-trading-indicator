# One-click "Export to Google Sheets" — setup (optional)

Closed trades are **always visible in the app** and downloadable as CSV with
zero setup. This adds a **one-click "📊 Export to Google Sheets"** button that
writes them straight into a Google Sheet you own — no database, no key file,
just one URL.

## Steps (~3 min)

1. Create a new **Google Sheet** (sheets.new). This is where trades land.
2. **Extensions → Apps Script.** Delete any code, paste this, and **Save**:

   ```javascript
   function doPost(e) {
     var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
     var data = JSON.parse(e.postData.contents);
     var rows = data.rows || [];
     var header = ["bot","symbol","base","side","entry","exit",
                   "pnl_usd","pnl_pct","qty","opened_at","exit_at","reason"];
     sheet.clear();                 // full replace -> no duplicates
     sheet.appendRow(header);
     rows.forEach(function (r) {
       sheet.appendRow(header.map(function (h) { return r[h]; }));
     });
     return ContentService
       .createTextOutput(JSON.stringify({ ok: true, written: rows.length }))
       .setMimeType(ContentService.MimeType.JSON);
   }
   ```

3. **Deploy → New deployment → Type: Web app.**
   - Execute as: **Me**
   - Who has access: **Anyone**
   - Click **Deploy**, authorize, and **copy the Web app URL**
     (looks like `https://script.google.com/macros/s/AKfy.../exec`).
4. Put that URL in **Streamlit secrets** (app → Settings → Secrets, or local
   `.streamlit/secrets.toml`):
   ```
   GSHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfy.../exec"
   ```
5. Reboot the app. A **📊 Export to Google Sheets** button now appears under
   the Closed Trades table in both Paper Trader and SST1. One click writes the
   full closed-trade history to your Sheet (it replaces the contents each time,
   so no duplicates).

## Notes
- The export **replaces** the sheet's contents with the current full history
  every time — so your Sheet always mirrors the app exactly.
- Until you set this up, just use **⬇ Download CSV** → in Google Sheets,
  **File → Import → Upload**.
- This is your durable record: even when a Streamlit redeploy wipes the app's
  in-memory trades, your Google Sheet keeps them. Export after trading sessions.
