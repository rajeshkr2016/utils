(function () {

  // ── CONFIG ───────────────────────────────────────────────────────
  const CONFIG = {
    DATES_TO_FILL: [],
    DATES_TO_EXCLUDE: ['05/25'],
    TIMES: ['09:00 AM', '01:00 PM', '01:30 PM', '05:30 PM'],
    EMPLOYEE_ID: '203',
    CAISO_ORG_LEVEL_ID: '7',
    CAISO_LABEL: 'CAISO',
    SKIP_DAYS: [0, 6]  // 0=Sun, 6=Sat
    // Examples:
    // DATES_TO_FILL: ['05/01', '05/05', '05/06'],
    // Leave [] to auto-fill ALL weekdays in the current view
  };
  // ─────────────────────────────────────────────────────────────────

  const DAY_NAMES = ['SUN','MON','TUE','WED','THU','FRI','SAT'];

  function getDayOfWeek(fullDate) {
    const [m, d, y] = fullDate.split('/');
    return new Date(`${y}-${m}-${d}T12:00:00`).getDay();
  }

  function setVal(el, val) {
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeSetter.call(el, val);
    ['input', 'change', 'blur'].forEach(e =>
      el.dispatchEvent(new Event(e, { bubbles: true }))
    );
  }

  function getWindowId(elId) {
    try {
      const enc = elId.split('__')[1];
      return String(JSON.parse(atob(enc))[0]);
    } catch (e) { return null; }
  }

  function getPunchId(elId) {
    try {
      const enc = elId.split('__')[1];
      return JSON.parse(atob(enc))[3]; // index 3 = punch_id
    } catch (e) { return null; }
  }

  function setCAISOdirect(selectEl) {
    const existing = Array.from(selectEl.options)
      .find(o => o.value === CONFIG.CAISO_ORG_LEVEL_ID);
    if (existing) {
      selectEl.value = CONFIG.CAISO_ORG_LEVEL_ID;
    } else {
      selectEl.innerHTML = `<option value="${CONFIG.CAISO_ORG_LEVEL_ID}">${CONFIG.CAISO_LABEL}</option>`;
      selectEl.value = CONFIG.CAISO_ORG_LEVEL_ID;
    }
    const s2 = document.getElementById('s2id_' + selectEl.id);
    if (s2) {
      const chosen = s2.querySelector('.select2-chosen');
      if (chosen) chosen.textContent = CONFIG.CAISO_LABEL;
      s2.setAttribute('title', CONFIG.CAISO_LABEL);
    }
    jQuery(selectEl).trigger('change');
  }

  // ── STEP 1: Read N/A Customer hours from Totals panel ─────────────
  function getNACustomerHours() {
    const panel = document.getElementById('timesheet-offcanvas-totals');
    if (!panel) return null;
    const allDTs = Array.from(panel.querySelectorAll('dt.left'));
    // Find the N/A dt that sits under the Customer section
    // (there are 2 N/A dt's — one under Customer, one under Overtime)
    // Customer's N/A comes before Overtime's N/A in document order
    const customerDT = allDTs.find(dt => dt.innerText?.trim() === 'Customer');
    if (!customerDT) return null;
    // Get the sub-dl that follows
    const subDL = customerDT.closest('dd')?.querySelector('dl') 
               || customerDT.parentElement?.nextElementSibling?.querySelector('dl')
               || Array.from(panel.querySelectorAll('dl.aside-subdl')).find(dl => {
                    // find the first aside-subdl that follows Customer label
                    const rect1 = customerDT.getBoundingClientRect();
                    const rect2 = dl.getBoundingClientRect();
                    return rect2.top > rect1.top;
                  });
    if (!subDL) {
      // Fallback: just check if any dt.left says N/A in the panel and has hours
      const naDTs = allDTs.filter(dt => dt.innerText?.trim() === 'N/A');
      for (const dt of naDTs) {
        const dd = dt.nextElementSibling;
        const hoursText = dd?.innerText?.replace(/\s+/g,'') || '';
        const hours = parseInt(hoursText);
        if (!isNaN(hours) && hours > 0) return hours;
      }
      return 0;
    }
    const naDT = Array.from(subDL.querySelectorAll('dt')).find(dt => dt.innerText?.trim() === 'N/A');
    if (!naDT) return 0;
    const dd = naDT.nextElementSibling;
    const hoursText = dd?.innerText?.replace(/\s+/g,'') || '';
    const match = hoursText.match(/(\d+)/);
    return match ? parseInt(match[1]) : 0;
  }

  // ── STEP 2: Delete all saved N/A punch rows ───────────────────────
  async function deleteNAPunches() {
    // Find all org_level selects with N/A AND punchId > 0 (actually saved)
    const allSels = Array.from(document.querySelectorAll('[id^="org_level_depth_2"]'));
    const savedNASels = allSels.filter(sel => {
      const punchId = getPunchId(sel.id);
      return punchId > 0 && sel.options[sel.selectedIndex]?.text === 'N/A';
    });

    if (savedNASels.length === 0) {
      console.log('✅ No saved N/A punches found — nothing to delete');
      return 0;
    }

    // Collect unique window_ids to avoid double-clicking
    const seenWindowIds = new Set();
    let deleted = 0;

    for (const sel of savedNASels) {
      const windowId = getWindowId(sel.id);
      if (seenWindowIds.has(windowId)) continue;
      seenWindowIds.add(windowId);

      const punchId = getPunchId(sel.id);
      const date = sel.closest('.timesheet-row-day[data-date]')?.getAttribute('data-date');

      // Find the delete link for this specific saved punch
      const deleteLink = document.querySelector(`a[id^="delete_punches__"][id$="${sel.id.split('__')[1]}"]`);
      if (!deleteLink) {
        console.warn(`⚠️ No delete link found for punchId ${punchId} on ${date}`);
        continue;
      }

      console.log(`🗑 Deleting saved N/A punch ${punchId} on ${date}`);
      deleteLink.click();
      deleted++;
      await new Promise(r => setTimeout(r, 200));
    }

    console.log(`🗑 Deleted ${deleted} saved N/A punch row(s)`);
    return deleted;
  }

  // ── STEP 3: Fill weekday punch times + CAISO ─────────────────────
  async function fillWeekdays() {
    const USE_DATE_LIST = CONFIG.DATES_TO_FILL.length > 0;
    const USE_EXCLUDE_LIST = CONFIG.DATES_TO_EXCLUDE.length > 0;

    console.log(USE_DATE_LIST
      ? `📋 Mode: specific dates → ${CONFIG.DATES_TO_FILL.join(', ')}`
      : `📋 Mode: all weekdays (auto)`
    );
    if (USE_EXCLUDE_LIST) console.log(`🚫 Excluding → ${CONFIG.DATES_TO_EXCLUDE.join(', ')}`);

    const dayRows = Array.from(document.querySelectorAll('.timesheet-row-day[data-date]'));
    const jobs = [];
    let skipped = 0;

    for (const dayRow of dayRows) {
      const fullDate = dayRow.getAttribute('data-date');
      const shortDate = fullDate.substring(0, 5);
      const dowIndex = getDayOfWeek(fullDate);
      const dayTxt = DAY_NAMES[dowIndex];

      if (CONFIG.SKIP_DAYS.includes(dowIndex)) { skipped++; continue; }
      if (USE_DATE_LIST && !CONFIG.DATES_TO_FILL.includes(shortDate)) { skipped++; continue; }
      if (USE_EXCLUDE_LIST && CONFIG.DATES_TO_EXCLUDE.includes(shortDate)) {
        console.log(`🚫 Excluding ${dayTxt} ${shortDate}`);
        skipped++;
        continue;
      }

      const indInput  = dayRow.querySelector('input[placeholder="IND"]');
      const inlInput  = dayRow.querySelector('input[placeholder="INL"]');
      const outInputs = Array.from(dayRow.querySelectorAll('input[placeholder="OUT"]'));

      if (!indInput) { skipped++; continue; }

      const indWindowId = getWindowId(indInput.id);
      const orgSelects = Array.from(
        dayRow.querySelectorAll('[id^="org_level_depth_2"]')
      ).filter(s => getWindowId(s.id) === indWindowId);

      jobs.push({ dayTxt, shortDate, indInput, inlInput, outInputs, orgSelects });
    }

    console.log(`📌 Days to fill (${jobs.length}): ${jobs.map(j => j.shortDate).join(', ')}`);

    let filled = 0;
    for (const { dayTxt, shortDate, indInput, inlInput, outInputs, orgSelects } of jobs) {
      // Set CAISO FIRST, then punch times
      if (orgSelects.length) {
        for (const sel of orgSelects) {
          setCAISOdirect(sel);
          await new Promise(r => setTimeout(r, 100));
        }
      }
      setVal(indInput,    CONFIG.TIMES[0]);
      if (outInputs[0]) setVal(outInputs[0], CONFIG.TIMES[1]);
      if (inlInput)     setVal(inlInput,     CONFIG.TIMES[2]);
      if (outInputs[1]) setVal(outInputs[1], CONFIG.TIMES[3]);

      console.log(`✅ Filled ${dayTxt} ${shortDate}`);
      filled++;
      await new Promise(r => setTimeout(r, 300));
    }
    return { filled, skipped };
  }

  // ── STEP 4: Validate Totals after save ───────────────────────────
  function checkTotalsAndAlert(filledCount) {
    // Open totals panel and read N/A hours
    const btn = document.getElementById('timesheet-totals-button');
    btn?.click();

    setTimeout(() => {
      const naHours = getNACustomerHours();
      const panel = document.getElementById('timesheet-offcanvas-totals');

      if (naHours === null) {
        alert(`⚠️ Could not read Totals panel.\n\nPlease open SHOW TOTALS manually and verify Customer → N/A shows 0h.`);
        return;
      }

      if (naHours > 0) {
        // Close the panel to let user see the timesheet
        alert(
          `⚠️ WARNING: Totals still show ${naHours}h under Customer → N/A!\n\n` +
          `This means some punches were saved with N/A customer.\n\n` +
          `DO NOT click SAVE yet.\n` +
          `Please review the timesheet for any remaining N/A rows and correct them manually, ` +
          `or re-run this script.`
        );
      } else {
        alert(
          `✅ All clear!\n\n` +
          `⏱ Days filled: ${filledCount}\n` +
          `🏢 Customer N/A hours: 0h ✓\n\n` +
          `Everything looks correct — click SAVE when ready.`
        );
      }
    }, 1200); // wait for totals panel to load
  }

  // ── MAIN ─────────────────────────────────────────────────────────
  async function run() {
    console.log('🚀 Starting cleanup + fill...');

    // Step 1: Delete saved N/A punches
    const deletedCount = await deleteNAPunches();
    if (deletedCount > 0) {
      console.log(`⏳ Waiting after deletions...`);
      await new Promise(r => setTimeout(r, 500));
    }

    // Step 2: Fill weekdays
    const { filled, skipped } = await fillWeekdays();

    // Step 3: Check totals
    console.log(`\n📊 Summary: filled=${filled}, skipped=${skipped}, deletedNAPunches=${deletedCount}`);
    console.log(`⚠️ REMINDER: Click SAVE, then the script will check Totals.`);

    // Prompt user to save first, then validate
    const doCheck = confirm(
      `✅ Fill complete!\n\n` +
      `📅 Days filled: ${filled}\n` +
      `🗑 Stale N/A punches deleted: ${deletedCount}\n\n` +
      `Click OK to open Totals and verify N/A = 0h.\n` +
      `(Save the timesheet first if you haven't already)`
    );

    if (doCheck) {
      checkTotalsAndAlert(filled);
    }
  }

  run();
})();