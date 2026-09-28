/*
 * page-rooms.js: rooms table + create/edit modal (admin).
 */

const ROOM_TYPES = ['lecture', 'lab', 'seminar'];

function initRooms({ content }) {
  content.innerHTML = pageHeader('Rooms', 'Lecture halls, labs and seminar rooms, with this semester’s weekly bookings.') + '<div id="list"></div>';

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/rooms',
    searchPlaceholder: 'Search building or room…',
    defaultSort: 'building',
    filters: [{ name: 'room_type', label: 'Type', options: ROOM_TYPES.map((t) => ({ value: t, label: titleCase(t) })) }],
    toolbarHtml: `<button type="button" id="new-room" class="${btnClass('primary')}">${icon('plus', 16)} New room</button>`,
    emptyIcon: 'door-open',
    columns: [
      { key: 'building', label: 'Building', sortable: true, render: (r) => `<span class="text-ink">${escapeHtml(r.building)}</span>` },
      { key: 'room_number', label: 'Room', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.room_number)}</span>` },
      { key: 'room_type', label: 'Type', sortable: true, render: (r) => badge(r.room_type === 'lab' ? 'info' : 'completed', titleCase(r.room_type)) },
      { key: 'capacity', label: 'Capacity', sortable: true, className: 'tabular-nums' },
      { key: 'weekly_classes', label: 'Weekly classes', sortable: true, render: (r) => `
          <div class="flex items-center gap-3 min-w-[140px]"><div class="flex-1">${progressBar((r.weekly_classes / 30) * 100)}</div>
          <span class="text-xs tabular-nums text-ink">${r.weekly_classes}</span></div>` },
      { key: 'actions', label: '', className: 'text-right', render: () => rowAction('edit', 'pencil', 'Edit') },
    ],
    onRowClick: (row) => openRoomForm(row),
    onAction: (action, row) => openRoomForm(row),
  });

  document.getElementById('new-room').addEventListener('click', () => openRoomForm(null));

  function openRoomForm(room) {
    const isEdit = Boolean(room);
    formModal({
      title: isEdit ? `Edit ${room.building} ${room.room_number}` : 'New room',
      submitText: isEdit ? 'Save changes' : 'Create room',
      fieldsHtml: `
        ${field({ name: 'building', label: 'Building', required: true, maxlength: 80, value: room?.building, placeholder: 'Academic Building A' })}
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-4">
          ${field({ name: 'room_number', label: 'Room number', required: true, maxlength: 20, value: room?.room_number, placeholder: '101' })}
          ${field({ name: 'capacity', label: 'Capacity', type: 'number', required: true, min: 1, max: 1000, step: 1, value: room?.capacity })}
          ${field({ name: 'room_type', label: 'Type', type: 'select', required: true, value: room?.room_type, options: ROOM_TYPES.map((t) => ({ value: t, label: titleCase(t) })) })}
        </div>`,
      onSubmit: (values) => (isEdit ? api.patch(`/rooms/${room.id}`, values) : api.post('/rooms', values)),
      onSuccess: (saved) => { toast(`${saved.building} ${saved.room_number} ${isEdit ? 'updated' : 'created'}`); list.reload(); },
    });
  }
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('rooms', 'Rooms');
if (session) initRooms(session);
