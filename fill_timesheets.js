(function(){

  // ── CONFIG — EDIT ONLY THIS SECTION ─────────────────────────────
  const CONFIG = {
    DATES_TO_FILL: [],
      //'05/01'
      //'04/16', '04/17', '04/20', '04/21', '04/22', '04/21'
      //'04/22', '04/23', '04/24',
      //'04/27', '04/28', '04/29', '04/30'
      
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

  const isVisible = (el) => !!(el && el.offsetParent !== null && el.getClientRects().length > 0);
  const visibleInputs = (root, sel) => Array.from(root.querySelectorAll(sel)).filter(isVisible);

  // Find all day label elements (MON, TUE, etc.) — visible only
  Array.from(document.querySelectorAll('*')).forEach(el => {
    if (el.children.length > 0) return;
    if (!isVisible(el)) return;
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
        e.children.length === 0 && isVisible(e) && /^\d{2}\/\d{2}$/.test((e.innerText||'').trim())
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

    // Find punch container (has visible IND, 2×OUT, INL inputs)
    let container = el, punchContainer = null;
    for (let i = 0; i < 12; i++) {
      container = container.parentElement; if (!container) break;
      const ind = visibleInputs(container, 'input[placeholder="IND"]');
      const outs = visibleInputs(container, 'input[placeholder="OUT"]');
      const inl = visibleInputs(container, 'input[placeholder="INL"]');
      if (ind.length >= 1 && outs.length >= 2 && inl.length >= 1) {
        punchContainer = container; break;
      }
    }
    if (!punchContainer) {
      console.warn(`⚠️ No punch container for ${dayTxt} ${dateStr}`);
      return;
    }

    // Find the day card: largest ancestor of punchContainer that still contains
    // exactly one visible IND input (i.e., does not bleed into another day).
    let dayCard = punchContainer;
    while (dayCard.parentElement) {
      const next = dayCard.parentElement;
      if (visibleInputs(next, 'input[placeholder="IND"]').length > 1) break;
      dayCard = next;
    }

    // Within the day card, locate ALL visible select2 widgets for org_level_depth_2,
    // then derive the underlying (hidden) selects. Some layouts have one customer
    // dropdown per punch row (Time/Category/Customer/Comment), so we need to set all.
    const orgSelects = Array.from(dayCard.querySelectorAll('[id^="s2id_"]'))
      .filter(s2 => isVisible(s2) && /org_level_depth_2/.test(s2.id))
      .map(s2 => document.getElementById(s2.id.replace(/^s2id_/, '')))
      .filter(Boolean);

    dayJobs.push({ dayTxt, dateStr, punchContainer, orgSelects });
  });

  console.log(`📌 Days to process: ${dayJobs.map(j => j.dateStr).join(', ')}`);

  async function run() {
    let filled = 0;
    for (const { dayTxt, dateStr, punchContainer, orgSelects } of dayJobs) {
      // Fill punch times — visible inputs only
      const ind = visibleInputs(punchContainer, 'input[placeholder="IND"]')[0];
      const inl = visibleInputs(punchContainer, 'input[placeholder="INL"]')[0];
      const outs = visibleInputs(punchContainer, 'input[placeholder="OUT"]');
      if (ind) setVal(ind, CONFIG.TIMES[0]);
      if (outs[0]) setVal(outs[0], CONFIG.TIMES[1]);
      if (inl) setVal(inl, CONFIG.TIMES[2]);
      if (outs[1]) setVal(outs[1], CONFIG.TIMES[3]);

      // Set CAISO on every customer dropdown belonging to this day
      if (dateStr && orgSelects && orgSelects.length) {
        console.log(`🏢 Setting CAISO on ${orgSelects.length} customer dropdown(s) for ${dateStr}`);
        for (const sel of orgSelects) {
          await setCAISOviaAPI(sel, dateStr);
        }
      }

      console.log(`✅ Filled ${dayTxt} ${dateStr}`);
      filled++;
      await new Promise(r => setTimeout(r, 300));
    }
    alert(`✅ Done!\n\n⏱ Days filled: ${filled}\n⏭ Days skipped: ${skipped}\n\nReview entries then click SAVE.`);
  }

  run();
})();