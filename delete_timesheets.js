(function () {

  // ── CONFIG — EDIT ONLY THIS SECTION ─────────────────────────────

  const CONFIG = {
    DATES_TO_DELETE: [],
    // Examples:
    // DATES_TO_DELETE: ['05/01', '05/05', '05/06'],
    // Leave [] to delete ALL entries in the current view

    SKIP_DAYS: ['SAT', 'SUN']
  };

  // ── END CONFIG ───────────────────────────────────────────────────

  const USE_DATE_LIST = CONFIG.DATES_TO_DELETE.length > 0;

  console.log(USE_DATE_LIST
    ? `📋 Mode: specific dates → ${CONFIG.DATES_TO_DELETE.join(', ')}`
    : `📋 Mode: all weekdays (auto)`
  );

  const dayRows = Array.from(document.querySelectorAll('.timesheet-row-day[data-date]'));
  const jobs = [];
  let skipped = 0;

  for (const dayRow of dayRows) {
    const fullDate = dayRow.getAttribute('data-date');
    const shortDate = fullDate.substring(0, 5);
    const dayWrap = dayRow.querySelector('.timesheet-col-day-wrap');
    const dayTxt = (dayWrap?.innerText || '').trim().toUpperCase().split('\n')[0];

    if (CONFIG.SKIP_DAYS.includes(dayTxt)) {
      skipped++;
      continue;
    }

    if (USE_DATE_LIST && !CONFIG.DATES_TO_DELETE.includes(shortDate)) {
      console.log(`⏭ Skipping ${dayTxt} ${shortDate}`);
      skipped++;
      continue;
    }

    // Get all trash links NOT already marked for undo (i.e. not yet clicked)
    const trashLinks = Array.from(
      dayRow.querySelectorAll('a.timesheet-trash-link:not(.undo-trash-link)')
    );

    if (trashLinks.length === 0) {
      console.log(`⏭ No punches to delete on ${dayTxt} ${shortDate}`);
      skipped++;
      continue;
    }

    jobs.push({ dayTxt, shortDate, trashLinks });
  }

  console.log(`📌 Days to delete (${jobs.length}): ${jobs.map(j => j.shortDate).join(', ')}`);

  async function run() {
    let totalDeleted = 0;

    for (const { dayTxt, shortDate, trashLinks } of jobs) {
      for (const link of trashLinks) {
        link.click();
        await new Promise(r => setTimeout(r, 100));
        totalDeleted++;
      }
      console.log(`🗑 Marked ${trashLinks.length} punch(es) for deletion on ${dayTxt} ${shortDate}`);
      await new Promise(r => setTimeout(r, 200));
    }

    alert(`🗑 Done!\n\n${totalDeleted} punch(es) marked for deletion across ${jobs.length} day(s).\n⏭ Days skipped: ${skipped}\n\n⚠️ Click SAVE to confirm the deletions.`);
  }

  run();

})();