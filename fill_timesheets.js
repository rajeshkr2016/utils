(function(){

  // ── CONFIG — EDIT ONLY THIS SECTION ─────────────────────────────
  const CONFIG = {
    DATES_TO_FILL: [ '04/16', '04/17', '04/20', '04/21'
      // '04/22', '04/23', '04/24',
      // '04/27', '04/28', '04/29', '04/30'
      ],
    // DATES_TO_FILL: [ ],
    // ↑ Set to [] to auto-fill ALL weekdays
    TIMES: ['09:00 AM', '01:00 PM', '01:30 PM', '05:30 PM'],
    EMPLOYEE_ID: '203',
    CAISO_ORG_LEVEL_ID: '7',
    SKIP_DAYS: ['SAT','SUN']
  };
  // ── END CONFIG ───────────────────────────────────────────────────

  function setVal(el, val) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    setter.call(el, val);
    ['input','change','blur'].forEach(e => el.dispatchEvent(new Event(e,{bubbles:true})));
  }

  function getWindowId(selectId) {
    try { return String(JSON.parse(atob(selectId.split('__')[1]))[0]); }
    catch(e) { return null; }
  }

  async function setCAISOviaAPI(selectEl, dateStr) {
    const windowId = getWindowId(selectEl.id);
    if (!windowId) { console.warn('No window_id for', selectEl.id); return false; }
    const onDate = `${dateStr}/${new Date().getFullYear()}`;
    const params = new URLSearchParams({
      action: 'load_levels', depth: '2',
      selected: JSON.stringify({"1":{"depth":1,"org_level_id":47},"2":{"depth":"2","org_level_id":CONFIG.CAISO_ORG_LEVEL_ID}}),
      required: '{}', ignore_empty_parents: '0',
      employee_id: CONFIG.EMPLOYEE_ID, on_date: onDate, window_id: windowId
    });
    try {
      await fetch('php/page/update_org_levels.php', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: params.toString()
      });
      jQuery(selectEl).val(CONFIG.CAISO_ORG_LEVEL_ID).trigger('change');
      const s2 = document.getElementById('s2id_' + selectEl.id);
      if (s2) {
        const r = s2.querySelector('.select2-chosen');
        if (r) r.textContent = 'CAISO';
        s2.setAttribute('title', 'CAISO');
      }
      console.log(`🏢 CAISO set: ${dateStr}`);
      return true;
    } catch(e) { console.error('API error:', e); return false; }
  }

  // ── MAIN LOGIC ───────────────────────────────────────────────────
  const USE_DATE_LIST = CONFIG.DATES_TO_FILL.length > 0;
  console.log(USE_DATE_LIST 
    ? `📋 Mode: specific dates → ${CONFIG.DATES_TO_FILL.join(', ')}`
    : `📋 Mode: all weekdays (auto)`
  );

  const dayJobs = [];
  let skipped = 0;

  // Find all day label elements (MON, TUE, etc.)
  Array.from(document.querySelectorAll('*')).forEach(el => {
    if (el.children.length > 0) return;
    const dayTxt = (el.innerText||'').trim().toUpperCase();
    if (!/^(MON|TUE|WED|THU|FRI|SAT|SUN)$/.test(dayTxt)) return;

    // Skip weekends always
    if (CONFIG.SKIP_DAYS.includes(dayTxt)) { skipped++; return; }

    // Find nearby date (MM/DD)
    let dateStr = null;
    let searchNode = el.parentElement;
    for (let i = 0; i < 6; i++) {
      if (!searchNode) break;
      const found = Array.from(searchNode.querySelectorAll('*')).find(e =>
        e.children.length === 0 && /^\d{2}\/\d{2}$/.test((e.innerText||'').trim())
      );
      if (found) { dateStr = found.innerText.trim(); break; }
      searchNode = searchNode.parentElement;
    }

    // ✅ KEY FIX: skip if dateStr is null OR not in list
    if (USE_DATE_LIST) {
      if (!dateStr || !CONFIG.DATES_TO_FILL.includes(dateStr)) {
        console.log(`⏭ Skipping ${dayTxt} ${dateStr||'(no date found)'}`);
        skipped++;
        return;
      }
    }

    // Find punch container (has IND, 2×OUT, INL inputs)
    let container = el, punchContainer = null;
    for (let i = 0; i < 12; i++) {
      container = container.parentElement; if (!container) break;
      if (container.querySelector('input[placeholder="IND"]') &&
          container.querySelectorAll('input[placeholder="OUT"]').length >= 2 &&
          container.querySelector('input[placeholder="INL"]')) {
        punchContainer = container; break;
      }
    }
    if (!punchContainer) {
      console.warn(`⚠️ No punch container for ${dayTxt} ${dateStr}`);
      return;
    }

    // Find org_level select (Customer dropdown)
    let orgSelect = null, sec = punchContainer;
    for (let i = 0; i < 5; i++) {
      sec = sec.parentElement; if (!sec) break;
      orgSelect = sec.querySelector('select[id*="org_level_depth_2"]');
      if (orgSelect) break;
    }

    dayJobs.push({ dayTxt, dateStr, punchContainer, orgSelect });
  });

  console.log(`📌 Days to process: ${dayJobs.map(j => j.dateStr).join(', ')}`);

  async function run() {
    let filled = 0;
    for (const { dayTxt, dateStr, punchContainer, orgSelect } of dayJobs) {
      // Fill punch times
      const ind = punchContainer.querySelector('input[placeholder="IND"]');
      const inl = punchContainer.querySelector('input[placeholder="INL"]');
      const outs = Array.from(punchContainer.querySelectorAll('input[placeholder="OUT"]'));
      if (ind) setVal(ind, CONFIG.TIMES[0]);
      if (outs[0]) setVal(outs[0], CONFIG.TIMES[1]);
      if (inl) setVal(inl, CONFIG.TIMES[2]);
      if (outs[1]) setVal(outs[1], CONFIG.TIMES[3]);

      // Set CAISO
      if (orgSelect && dateStr) await setCAISOviaAPI(orgSelect, dateStr);

      console.log(`✅ Filled ${dayTxt} ${dateStr}`);
      filled++;
      await new Promise(r => setTimeout(r, 300));
    }
    alert(`✅ Done!\n\n⏱ Days filled: ${filled}\n⏭ Days skipped: ${skipped}\n\nReview entries then click SAVE.`);
  }

  run();
})();