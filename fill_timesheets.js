(function () {

  // ── CONFIG — EDIT ONLY THIS SECTION ─────────────────────────────
  const CONFIG = {
    DATES_TO_FILL: [],
    // Examples:
    // DATES_TO_FILL: ['05/01', '05/05', '05/06'],
    // Leave [] to auto-fill ALL weekdays in the current view

    TIMES: ['09:00 AM', '01:00 PM', '01:30 PM', '05:30 PM'],
    EMPLOYEE_ID: '203',
    CAISO_ORG_LEVEL_ID: '7',
    SKIP_DAYS: ['SAT', 'SUN']
  };
  // ── END CONFIG ───────────────────────────────────────────────────

  // React-compatible value setter that triggers onChange
  function setVal(el, val) {
    const nativeInputSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputSetter.call(el, val);
    ['input', 'change', 'blur'].forEach(evtName =>
      el.dispatchEvent(new Event(evtName, { bubbles: true }))
    );
  }

  // Decode window_id from the select element's ID attribute
  function getWindowId(selectId) {
    try {
      const encoded = selectId.split('__')[1];
      return String(JSON.parse(atob(encoded))[0]);
    } catch (e) {
      return null;
    }
  }

  // Call the API to load CAISO options into the dropdown, then set it
  async function setCAISOviaAPI(selectEl, fullDate) {
    const windowId = getWindowId(selectEl.id);
    if (!windowId) {
      console.warn('⚠️ No window_id for', selectEl.id);
      return false;
    }

    const params = new URLSearchParams({
      action: 'load_levels',
      depth: '2',
      selected: JSON.stringify({
        "1": { "depth": 1, "org_level_id": 47 },
        "2": { "depth": "2", "org_level_id": CONFIG.CAISO_ORG_LEVEL_ID }
      }),
      required: '1',                        // FIX: was '{}', must be '1'
      ignore_empty_parents: '0',
      employee_id: CONFIG.EMPLOYEE_ID,
      on_date: fullDate,                     // FIX: full MM/DD/YYYY from data-date
      window_id: windowId
    });

    try {
      await fetch('php/page/update_org_levels.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString()
      });

      // Set via jQuery (triggers select2 UI update)
      jQuery(selectEl).val(CONFIG.CAISO_ORG_LEVEL_ID).trigger('change');

      // Also update the select2 display label if present
      const s2 = document.getElementById('s2id_' + selectEl.id);
      if (s2) {
        const chosen = s2.querySelector('.select2-chosen');
        if (chosen) chosen.textContent = 'CAISO';
        s2.setAttribute('title', 'CAISO');
      }

      console.log(`🏢 CAISO set [${fullDate}] windowId=${windowId}`);
      return true;
    } catch (e) {
      console.error('❌ API error for', fullDate, e);
      return false;
    }
  }

  // ── MAIN ─────────────────────────────────────────────────────────

  // Determine if we're filtering to specific dates
  const USE_DATE_LIST = CONFIG.DATES_TO_FILL.length > 0;
  console.log(USE_DATE_LIST
    ? `📋 Mode: specific dates → ${CONFIG.DATES_TO_FILL.join(', ')}`
    : `📋 Mode: all weekdays (auto)`
  );

  // Collect all day rows from the DOM using reliable data-date containers
  const dayRows = Array.from(document.querySelectorAll('.timesheet-row-day[data-date]'));
  const jobs = [];
  let skipped = 0;

  for (const dayRow of dayRows) {
    const fullDate = dayRow.getAttribute('data-date'); // e.g. "05/01/2026"
    const shortDate = fullDate.substring(0, 5);         // e.g. "05/01"
    const dayWrap = dayRow.querySelector('.timesheet-col-day-wrap');
    const dayTxt = (dayWrap?.innerText || '').trim().toUpperCase().split('\n')[0]; // MON, TUE, etc.

    // Skip weekends
    if (CONFIG.SKIP_DAYS.includes(dayTxt)) {
      skipped++;
      continue;
    }

    // Filter by date list if set
    if (USE_DATE_LIST && !CONFIG.DATES_TO_FILL.includes(shortDate)) {
      console.log(`⏭ Skipping ${dayTxt} ${shortDate}`);
      skipped++;
      continue;
    }

    // Find punch time inputs within this day row
    const indInput  = dayRow.querySelector('input[placeholder="IND"]');
    const inlInput  = dayRow.querySelector('input[placeholder="INL"]');
    const outInputs = Array.from(dayRow.querySelectorAll('input[placeholder="OUT"]'));

    if (!indInput) {
      console.warn(`⚠️ No IND input for ${dayTxt} ${shortDate} — skipping`);
      skipped++;
      continue;
    }

    // Find ALL org level customer selects for this day
    const orgSelects = Array.from(
      dayRow.querySelectorAll('[id^="org_level_depth_2"]')
    );

    jobs.push({ dayTxt, shortDate, fullDate, indInput, inlInput, outInputs, orgSelects });
  }

  console.log(`📌 Days to process (${jobs.length}): ${jobs.map(j => j.shortDate).join(', ')}`);

  async function run() {
    let filled = 0;

    for (const { dayTxt, shortDate, fullDate, indInput, inlInput, outInputs, orgSelects } of jobs) {
      // Fill punch times
      setVal(indInput,    CONFIG.TIMES[0]); // 09:00 AM  IND
      if (outInputs[0]) setVal(outInputs[0], CONFIG.TIMES[1]); // 01:00 PM  OUT
      if (inlInput)     setVal(inlInput,     CONFIG.TIMES[2]); // 01:30 PM  INL
      if (outInputs[1]) setVal(outInputs[1], CONFIG.TIMES[3]); // 05:30 PM  OUT

      // Set CAISO on every customer dropdown for this day
      if (orgSelects.length) {
        console.log(`🏢 Setting CAISO on ${orgSelects.length} customer dropdown(s) for ${shortDate}`);
        for (const sel of orgSelects) {
          await setCAISOviaAPI(sel, fullDate);
          await new Promise(r => setTimeout(r, 150)); // small gap between API calls
        }
      }

      console.log(`✅ Filled ${dayTxt} ${shortDate}`);
      filled++;
      await new Promise(r => setTimeout(r, 300));
    }

    alert(`✅ Done!\n\n⏱ Days filled: ${filled}\n⏭ Days skipped: ${skipped}\n\nReview entries then click SAVE.`);
  }

  run();
})();