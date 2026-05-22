(function () {

  const CONFIG = {
    DATES_TO_FILL: [],
    TIMES: ['09:00 AM', '01:00 PM', '01:30 PM', '05:30 PM'],
    EMPLOYEE_ID: '203',
    CAISO_ORG_LEVEL_ID: '7',
    SKIP_DAYS: ['SAT', 'SUN']
  };

  function setVal(el, val) {
    const nativeInputSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputSetter.call(el, val);
    ['input', 'change', 'blur'].forEach(evtName =>
      el.dispatchEvent(new Event(evtName, { bubbles: true }))
    );
  }

  function setCAISO(selectEl) {
    const caisoOpt = Array.from(selectEl.options).find(o => o.text === 'CAISO');
    const targetVal = caisoOpt ? caisoOpt.value : CONFIG.CAISO_ORG_LEVEL_ID;

    // Inject option if not present
    if (!Array.from(selectEl.options).find(o => o.value === targetVal)) {
      selectEl.add(new Option('CAISO', targetVal, false, false));
    }

    selectEl.value = targetVal;
    jQuery(selectEl).trigger('change'); // ← KEY: adds to changed_rows so server accepts the value

    // Update select2 display
    const s2 = document.getElementById('s2id_' + selectEl.id);
    if (s2) {
      const chosen = s2.querySelector('.select2-chosen');
      if (chosen) chosen.textContent = 'CAISO';
      s2.setAttribute('title', 'CAISO');
    }
    return true;
  }

  const USE_DATE_LIST = CONFIG.DATES_TO_FILL.length > 0;
  const dayRows = Array.from(document.querySelectorAll('.timesheet-row-day[data-date]'));
  const jobs = [];
  let skipped = 0;

  for (const dayRow of dayRows) {
    const fullDate = dayRow.getAttribute('data-date');
    const shortDate = fullDate.substring(0, 5);
    const dayWrap = dayRow.querySelector('.timesheet-col-day-wrap');
    const dayTxt = (dayWrap?.innerText || '').trim().toUpperCase().split('\n')[0];

    if (CONFIG.SKIP_DAYS.includes(dayTxt)) { skipped++; continue; }
    if (USE_DATE_LIST && !CONFIG.DATES_TO_FILL.includes(shortDate)) { skipped++; continue; }

    const indInput  = dayRow.querySelector('input[placeholder="IND"]');
    const inlInput  = dayRow.querySelector('input[placeholder="INL"]');
    const outInputs = Array.from(dayRow.querySelectorAll('input[placeholder="OUT"]'));

    if (!indInput) { skipped++; continue; }

    const orgSelects = Array.from(dayRow.querySelectorAll('[id^="org_level_depth_2"]'))
      .filter(s => {
        // Skip TXO template rows (punchId=0)
        try { return JSON.parse(atob(s.id.split('__')[1]))[3] > 0; } catch(e) { return true; }
      });

    jobs.push({ dayTxt, shortDate, indInput, inlInput, outInputs, orgSelects });
  }

  console.log(`📌 Days to process (${jobs.length}): ${jobs.map(j => j.shortDate).join(', ')}`);

  async function run() {
    let filled = 0;
    for (const { dayTxt, shortDate, indInput, inlInput, outInputs, orgSelects } of jobs) {
      setVal(indInput,    CONFIG.TIMES[0]);
      if (outInputs[0]) setVal(outInputs[0], CONFIG.TIMES[1]);
      if (inlInput)     setVal(inlInput,     CONFIG.TIMES[2]);
      if (outInputs[1]) setVal(outInputs[1], CONFIG.TIMES[3]);

      for (const sel of orgSelects) {
        setCAISO(sel);
        await new Promise(r => setTimeout(r, 50));
      }

      console.log(`✅ Filled ${dayTxt} ${shortDate}`);
      filled++;
      await new Promise(r => setTimeout(r, 200));
    }
    alert(`✅ Done!\n\n⏱ Days filled: ${filled}\n⏭ Days skipped: ${skipped}\n\nReview then click SAVE.`);
  }

  run();
})();