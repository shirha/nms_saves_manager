let leftSelected = null;
let rightSelected = null;
let histSelected = false;
let timeLedger = null;

// Add these here so they're global:
let currentView = 'pool';

function updateDebugState() {
  $('#debugState').html(`
    <b>View:</b> ${currentView}
    <br><b>leftSelected:</b> ${leftSelected ? JSON.stringify(leftSelected) : 'null'}
    <br><b>rightSelected:</b> ${rightSelected ? JSON.stringify(rightSelected) : 'null'}
  `);
}

/**
 * Displays a temporary message in the UI message area using Bootstrap alert styling.
 * Clears any existing message and shows the new one with the specified class (e.g., 'alert-success').
 *
 * @param {string} msg - The message text to display (supports HTML).
 * @param {string} [cls='alert-info'] - Bootstrap alert class (e.g., 'alert-success', 'alert-danger').
 * @global
 */
function showMessage(msg, cls='alert-info') {
  $('#message').html(`<div class="alert ${cls}">${msg}</div>`);
}

/**
 * Finalizes UI updates after all reloads complete.
 * - Waits for all provided reload promises to finish
 * - Runs scanForMismatches
 * - Shows a success message
 * - Clears selection and table-active states
 *
 * @param {Promise[]} reloads - Array of jqXHR or Promise objects (e.g., [reloadPool(), reloadSaves()])
 * @param {string} message - Success message to display
 * @param {string} [cls='alert-success'] - Bootstrap alert class
 */
function finishAndNotify(reloads, message, cls='alert-success') {
  // Wait for all reloads to finish
  $.when.apply($, reloads).done(() => {
    scanForMismatches();
    // Clear table highlights and selections
    $('#leftList .table-active').removeClass('table-active');
    $('#rightList .table-active').removeClass('table-active');
    leftSelected = null;
    rightSelected = null;
    updateDebugState();

    showMessage(message, cls);
  }).fail(() => {
    showMessage('One or more reloads failed', 'alert-warning');
  });
}

/**
 * Scans for mismatches between pool and saves for slots 1-15.
 * Compares modification times (mtime); highlights right-side rows in yellow (table-warning)
 * if saves mtime > pool mtime (indicating unsynced changes).
 * Run after reloads to visually flag backups needed.
 *
 * @global {boolean} histSelected - If true, skips scanning (history view active).
 * @example
 * reloadPool().done(scanForMismatches);  // Check after pool load
 */
function scanForMismatches() {
  for (let i = 1; i <= 15; i++) {
    const rightRow = $('#rightList tbody tr:nth-child(' + i + ')');
    const rightMtime = rightRow.find('td:nth-child(2)').text().trim();
    // const leftRow = $('#leftList tbody tr:nth-child(' + i + ')');
    // const leftMtime = leftRow.find('td:nth-child(2)').text().trim();
    rightRow.removeClass('table-warning');
    // if (rightMtime && (!leftMtime || rightMtime > leftMtime)) {
    if (rightMtime && !(rightMtime in timeLedger)) {
      rightRow.addClass('table-warning');  // Orange/yellow warning on whole row
    // use dataset instead of td !!  
    }
  }
}

/**
 * Reloads and renders the active saves table in the right panel (#rightList).
 * Fetches save data from /api/saves, generates a Bootstrap table with slots 1-15,
 * and sets up click handlers for row selection. Empty slots are styled light gray.
 * Updates global rightSelected on selection/deselection.
 *
 * @async
 * @global {Object} rightSelected - Updated with {slot, path} on row click.
 * @returns {jQuery.jqXHR} - The AJAX promise for the GET request.
 *
 * @example
 * reloadSaves();  // Refreshes the saves table
 *
 * @throws {Error} If API fails (handled by jQuery error callback, not shown).
 * @see {@link https://api.jquery.com/jQuery.get/|$.get docs}
 */

function reloadSaves() {
  // Show spinner while loading
  showMessage(`
    <div class="d-flex align-items-center">
      <div class="spinner-border text-primary me-2" role="status" style="width: 1rem; height: 1rem;">
        <span class="visually-hidden">Loading...</span>
      </div>
      <span>Loading Saves...</span>
    </div>
  `, 'alert-secondary');

  return $.get('/api/saves', data => {
    const container = $('#rightList').empty();
    const slotMap = {};
    data.forEach(it => {
      slotMap[it.slot] = it;
    });

    const table = $('<table class="table table-sm table-hover"></table>');
    const thead = $('<thead class="table-light"><tr><th>Slot</th><th>Modified</th><th>Runtime</th><th>Saves Name</th></tr></thead>');
    table.append(thead);

    const tbody = $('<tbody></tbody>');
    for (let i = 1; i <= 15; i++) {
      const slotStr = i.toString();
      const it = slotMap[slotStr] || { slot: i, path: '', mtime: '', runtime: '', savename: '' };
      const rowClass = it.path ? '' : 'table-light';
      const tr = $(`<tr class="${rowClass}" data-slot="${it.slot}" data-mtime="${it.mtime}" data-path="${it.path}">
        <td>${it.slot}</td><td>${it.mtime}</td><td>${it.runtime}</td><td>${it.savename}</td>
      </tr>`);

      tr.click(() => {
        if (tr.hasClass('table-active')) {
          $('#rightList .table-active').removeClass('table-active');
          rightSelected = null;
          updateDebugState();
          showMessage("&nbsp;", 'alert-secondary');
        } else {
          $('#rightList .table-active').removeClass('table-active');
          tr.addClass('table-active');
          rightSelected = {
            slot: it.slot,
            path: it.path || '',
            mtime: it.mtime
          };
          updateDebugState();

          if (it.mtime) { 
            if (timeLedger[it.mtime]) {
              showMessage(`<b>Pool</b> backup in slot ${timeLedger[it.mtime]}`, 'alert-secondary');
            } else {
              showMessage('No <b>Pool</b> backup', 'alert-secondary');
            }
          } else {
            showMessage('&nbsp;', 'alert-secondary');
          }
        }
      });

      tbody.append(tr);
    }

    table.append(tbody);
    container.append(table);

    // Replace spinner with success message
    showMessage('Showing Saves', 'alert-success');
  })
  .fail(() => {
    showMessage('Failed to load saves', 'alert-danger');
  });
}

/**
 * Reloads and renders the pool table in the left panel (#leftList).
 * Fetches pool data from /api/pool, generates a Bootstrap table with slots 1-15,
 * and sets up click handlers for row selection. Empty slots are styled light gray;
 * slots with notes get a blue info class on the slot cell.
 * Resets global histSelected to false.
 *
 * @async
 * @global {Object} leftSelected - Updated with {slot, path} on row click.
 * @global {boolean} histSelected - Set to false after load.
 * @returns {jQuery.jqXHR} - The AJAX promise for the GET request.
 *
 * @example
 * reloadPool().done(scanForMismatches);  // Refreshes pool and checks mismatches
 *
 * @throws {Error} If API fails (handled by jQuery error callback, not shown).
 * @see {@link https://api.jquery.com/jQuery.get/|$.get docs}
 */
function reloadPool() {
  return $.get('/api/pool', data => {
    timeLedger = data.ledger
    const container = $('#leftList').empty();
    // Create slot map for quick lookup
    const slotMap = {};
    data.pool.forEach(it => {
      slotMap[it.slot] = it;
    });
    // Create table
    const table = $('<table class="table table-sm table-hover"></table>');
    // Header
    const thead = $('<thead class="table-light"><tr><th>Slot</th><th>Modified</th><th>Runtime</th><th>Saves Name</th></tr></thead>');
    table.append(thead);
    const tbody = $('<tbody></tbody>');
    // Generate rows for current pool slots 1-15
    for (let i = 1; i <= 15; i++) {
      // const slotStr = i.toString();
      const it = slotMap[i] || { slot: i, path: '', mtime: '', runtime: '', savename: '' };
      const rowClass = it.path ? '' : 'table-light'; // Light gray for empty slots

      const tr = $(`<tr class="${rowClass}" data-slot="${it.slot}" data-mtime="${it.mtime}" data-path="${it.path}">
        <td class="${it.note ? 'table-info' : ''}">${it.slot}</td>
        <td>${it.mtime}</td><td>${it.runtime}</td><td>${it.savename}</td>
      </tr>`);

      tr.click(() => {
        if (tr.hasClass('table-active')) {
          $('#leftList .table-active').removeClass('table-active');
          leftSelected = null;
          updateDebugState();
        } else {
          $('#leftList .table-active').removeClass('table-active');
          tr.addClass('table-active');
          leftSelected = {
            slot: it.slot,
            path: it.path || '',
            mtime: it.mtime
          };
          updateDebugState();
        }
      });
      tbody.append(tr);
    }
    table.append(tbody);
    container.append(table);
    histSelected = false;
  });
}

/**
 * Reloads and renders the history table for a specific slot in the left panel (#leftList).
 * Fetches history data from /api/history/<slot>, generates a Bootstrap table with all entries,
 * and sets up click handlers for row selection. Entries without paths are styled light gray.
 * Auto-selects the first data row (eq(1), skipping header). Sets global histSelected to true.
 *
 * @async
 * @global {Object} leftSelected - Updated with {slot, path} on row click (path fallback to '').
 * @global {boolean} histSelected - Set to true on success.
 * @param {Object} leftSelected - Global with .slot (required for API URL).
 * @returns {jQuery.jqXHR} - The AJAX promise for the GET request.
 *
 * @example
 * // Call after selecting a pool slot
 * reloadHist();  // Shows history for leftSelected.slot
 *
 * @throws {Error} If API fails (handled by jQuery error callback, not shown).
 * @see {@link https://api.jquery.com/jQuery.get/|$.get docs}
 */
function reloadHist() {
  return $.get(`/api/history/${leftSelected.slot}`, data=>{
    timeLedger = data.ledger
    const container = $('#leftList').empty();
    // Create table
    const table = $('<table class="table table-sm table-hover"></table>');
    // Header
    const thead = $('<thead class="table-light"><tr><th>Slot</th><th>Modified</th><th>Runtime</th><th>Saves Name</th></tr></thead>');
    table.append(thead);
    const tbody = $('<tbody></tbody>');
    // Generate rows for history for selected slot
    data.pool.forEach(it => {
      const rowClass = it.path ? '' : 'table-light'; // Light gray if no path, though unlikely

      const tr = $(`<tr class="${rowClass}" data-slot="${it.slot}" data-mtime="${it.mtime}" data-path="${it.path}">
        <td class="${it.note ? 'table-info' : ''}">${it.slot}</td>
        <td>${it.mtime}</td><td>${it.runtime}</td><td>${it.savename}</td>
      </tr>`);

      tr.click(() => {
        if (tr.hasClass('table-active')) {
          $('#leftList .table-active').removeClass('table-active');
          leftSelected = null;
          updateDebugState();
        } else {
          $('#leftList .table-active').removeClass('table-active');
          tr.addClass('table-active');
          leftSelected = {
            slot: it.slot,
            path: it.path || '',
            mtime: it.mtime
          };
          // lastHistoryMtime = it.mtime; // remember last viewed
          // lastHistorySlot = it.slot; // remember last viewed
          updateDebugState();
        }
      });
      tbody.append(tr);
    });
    table.append(tbody);
    container.append(table);
    histSelected = true;
  });
}

$(document).ready(()=>{
  let currentNotePath = null;

  $('#btnSaves').click(()=>{ reloadSaves().done(scanForMismatches); });
 
  // --- POOL VIEW ---
  $('#btnPool').click(() => {
    currentView = 'pool';
    updateDebugState();

    reloadPool().done(() => {
      showMessage('Showing Pool (most current per slot)', 'alert-secondary');

      // Try to rehighlight only if mtime still exists
      if (leftSelected && leftSelected.mtime) {
        const match = $(`#leftList tbody tr`).filter((_, tr) =>
          $(tr).data('mtime') === leftSelected.mtime
        );
        if (match.length) {
          match.addClass('table-active');
        }
      }
    });
  });

  // --- HISTORY VIEW ---
  $('#btnHistory').click(() => {
    // must have a pool selection first
    if (!leftSelected || !leftSelected.mtime) {
      showMessage('Select a <b>Pool</b> slot first', 'alert-warning');
      return;
    }

    currentView = 'history';
    updateDebugState();

    reloadHist().done(() => {
      showMessage('Showing history for slot ' + leftSelected.slot, 'alert-secondary');

      // Try to rehighlight only if mtime still exists
      if (leftSelected && leftSelected.mtime) {
        const match = $(`#leftList tbody tr`).filter((_, tr) =>
          $(tr).data('mtime') === leftSelected.mtime
        );
        if (match.length) {
          match.addClass('table-active');
        }
      }
    });
  });

  // Pool to Saves
  $('#btnCopyToSaves').click(() => {
    if (!leftSelected) {
      showMessage('Select a <b>Pool</b> or <b>History</b> slot on the left', 'alert-warning');
      return;
    }
    if (!rightSelected) {
      showMessage('Select a <b>Saves</b> slot on the right', 'alert-warning');
      return;
    }
    // Confirm copy (mention auto-backup if needed)
    const confirmMsg = `Copy Pool "${leftSelected.path}" to Saves slot ${rightSelected.slot}? Existing save will be auto-backed up to pool`;
    if (confirm(confirmMsg)) {
      $.ajax({
        url: '/api/copy',
        method: 'POST',
        contentType: 'application/json',                   
        data: JSON.stringify({ 
          src_slot: leftSelected.slot,  // needed to check for missing src
          src_path: leftSelected.path, 
          dst_slot: rightSelected.slot,
          dst_path: rightSelected.path  // needed in case of dst overwrite
        }),
        success: function (res) {
          if (!res.ok) showMessage(res.error, 'alert-danger');

          // Build list of reloads we’ll wait for
          const reloads = [];
          if (res.backup) reloads.push(histSelected ? reloadHist() : reloadPool());
          reloads.push(reloadSaves());

          const backupNote = res.backup ? " (auto-backup taken)" : ""; // ?????????????????
          // Run all reloads, then finalize
          finishAndNotify(reloads, res.content + backupNote);
        },
        error: function () {
          showMessage('Copy failed', 'alert-danger');
        }
      });
    }
  });

  // Backup Saves
  $('#btnCopyToPool').click(() => {
    const highlighted = $('#rightList tbody tr.table-warning');
    console.log(highlighted)

    // === Case 1: no row selected ===
    if (!rightSelected || !rightSelected.path) {
      if (highlighted.length === 0) {
        showMessage('Select a <b>Saves</b> file on the right or have highlighted rows to back up', 'alert-warning');
        return;
      }

      // Confirm bulk backup
      if (!confirm(`Backup ALL ${highlighted.length} highlighted saves to Pool?`)) return;

      // Iterate through highlighted rows sequentially
      const rows = Array.from(highlighted);
      let completed = 0;

      function backupNext() {
        if (completed >= rows.length) {
          // all done
          finishAndNotify([reloadPool(), reloadSaves()], `Backed up ${rows.length} saves to Pool`, 'alert-success');
          return;
        }

        const row = $(rows[completed]);
        const slot = row.data('slot');
        const path = row.data('path');
        console.log(`slot= ${slot}, path=${path}`)
        showMessage(`Backing up slot ${slot}... (${completed + 1}/${rows.length})`, 'alert-info');

        $.ajax({
          url: '/api/backup',
          method: 'POST',
          contentType: 'application/json',
          data: JSON.stringify({ slot: slot, path: path }),
          success: function (res) {
            if (res.ok) {
              console.log(`✓ slot ${slot} backed up`);
            } else {
              console.warn(`✗ slot ${slot} failed: ${res.error}`);
            }
          },
          error: function (xhr) {
            console.warn(`✗ slot ${slot} AJAX error`, xhr.statusText);
          },
          complete: function () {
            completed++;
            backupNext(); // next one
          }
        });
      }

      backupNext(); // start chain
      return; // stop single backup branch
    }

    // === Case 2: normal single backup ===
    $.ajax({
      url: '/api/backup',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({ slot: rightSelected.slot, path: rightSelected.path }),
      success: function (res) {
        if (!res.ok) return showMessage(res.error, 'alert-danger');
        finishAndNotify([histSelected ? reloadHist() : reloadPool()], res.content, res.color);
      },
      error: function () {
        showMessage('Backup failed', 'alert-danger');
      }
    });
  });

  $('#btnDelete').click(() => {
    // Ignore leftSelected if it's hidden (no active row visible)
    if ($('#leftList tbody tr.table-active').length === 0) {
      leftSelected = null;
      updateDebugState();
    }

    if( !leftSelected === !rightSelected) {
      showMessage('Select only one entry to delete', 'alert-warning');
      return;
    }
    showMessage('&nbsp;', 'alert-secondary');

    // Simple confirm dialog
    if (confirm(`Are you sure you want to delete this entry? This cannot be undone.`)) {
      $.ajax({
        url: '/api/delete',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ 
          pool_path: leftSelected && leftSelected.path,  
          saves_slot: rightSelected && rightSelected.slot, 
          saves_path: rightSelected && rightSelected.path, 
          hist_selected: histSelected 
        }),
        success: function (res) {
          if (!res.ok) return showMessage(res.error, 'alert-danger');

          const successMsg = res.right
            ? `<b>Saves</b> slot ${rightSelected && rightSelected.path} deleted`
            : `<b>Pool</b> path ${leftSelected && leftSelected.path} deleted`;
          const backupNote = res.backup ? " (auto-backup taken)" : "";


          // Build list of reloads we’ll wait for
          const reloads = [];
          if (res.right) reloads.push(reloadSaves());
          if (res.backup) reloads.push(histSelected ? reloadHist() : reloadPool());
          if (!res.right && !res.backup) reloads.push(histSelected ? reloadHist() : reloadPool());

          // Run all reloads, then finalize
          finishAndNotify(reloads, successMsg + backupNote);
        }
      });
    }
  });

  $('#btnNote').click(() => {
    if (!leftSelected) {
      showMessage('Select a pool/history entry first', 'alert-warning');
      return;
    }
    // Fetch existing note
    $.get('/api/note', { path: leftSelected.path })
      .done(data => {
        $('#noteSlot').text(leftSelected.slot);
        $('#noteContent').val(data.content || '');
        currentNotePath = leftSelected.path;
        
        // Show/hide Delete button based on existing content
        if (data.content && data.content.trim()) {
          $('#deleteNoteBtn').show();
        } else {
          $('#deleteNoteBtn').hide();
        }
        
        new bootstrap.Modal(document.getElementById('noteModal')).show();
      })
      .fail(() => showMessage('Failed to load note', 'alert-danger'));
  });

  $('#saveNoteBtn').click(() => {
    const content = $('#noteContent').val().trim();
    if (currentNotePath) {
      $.ajax({
        url: '/api/note',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ path: currentNotePath, content: content }),
        success: (res) => {
          if (res.ok) {
            showMessage('Note saved', 'alert-success');
            bootstrap.Modal.getInstance(document.getElementById('noteModal')).hide();
            currentNotePath = null;
            if (histSelected) { reloadHist(); } else { reloadPool(); }
          } else {
            showMessage(res.error, 'alert-danger');
          }
        },
        error: () => showMessage('Failed to save note', 'alert-danger')
      });
    }
  });

  $('#deleteNoteBtn').click(() => {
    if (currentNotePath && confirm('Are you sure you want to delete this note? This cannot be undone.')) {
      $.ajax({
        url: '/api/note',
        method: 'DELETE',
        contentType: 'application/json',
        data: JSON.stringify({ path: currentNotePath }),
        success: (res) => {
          if (res.ok) {
            showMessage('Note deleted', 'alert-success');
            $('#noteContent').val('');  // Clear the textarea
            $('#deleteNoteBtn').hide();  // Hide the button
            bootstrap.Modal.getInstance(document.getElementById('noteModal')).hide();
            if (histSelected) { reloadHist(); } else { reloadPool(); }
          } else {
            showMessage(res.error, 'alert-danger');
          }
        },
        error: () => showMessage('Failed to delete note', 'alert-danger')
      });
    }
  });
// initial load
  finishAndNotify([reloadPool(), reloadSaves()], '&nbsp;', 'alert-secondary');
});
/*
// Keyboard shortcuts: 'r' for robo, 'b' for build
$(document).on('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;  // Skip if typing in form fields

  if (e.key === 'r') {
    e.preventDefault();
    let msg = prompt("msg:", '')
    $.ajax({
      url: '/api/robo',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({'msg': msg}),  // Empty body; add params if needed later
      success: (res) => {
        if (res.ok) {
          showMessage(res.content || 'Robocopy started', 'alert-success');
        } else {
          showMessage(res.error, 'alert-danger');
        }
      },
      error: () => showMessage('Robo request failed', 'alert-danger')
    });
  } else if (e.key === 'b') {
    e.preventDefault();
    $.ajax({
      url: '/api/build',
      method: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({}),  // Empty body; add params if needed later
      success: (res) => {
        if (res.ok) {
          histSelected ? reloadHist().done(scanForMismatches) 
                       : reloadPool().done(scanForMismatches)
          showMessage(res.content || 'Build started', 'alert-success');
        } else {
          showMessage(res.error, 'alert-danger');
        }
      },
      error: () => showMessage('Pool build request failed', 'alert-danger')
    });
  }
});
*/
// At end of app.js
window.showMessage = showMessage;
window.finishAndNotify = finishAndNotify;
window.reloadSaves = reloadSaves;
window.reloadPool = reloadPool;
window.reloadHist = reloadHist;
window.scanForMismatches = scanForMismatches;