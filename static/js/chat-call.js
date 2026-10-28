(() => {
  const dialog = document.getElementById('chat-call-dialog');
  if (!dialog) return;
  const status = document.getElementById('call-status');
  const remote = document.getElementById('call-remote');
  const local = document.getElementById('call-local');
  const incomingControls = document.getElementById('call-incoming-controls');
  const activeControls = document.getElementById('call-active-controls');
  const closeButton = document.getElementById('call-close');
  const micButton = document.getElementById('call-mic');
  const cameraButton = document.getElementById('call-camera');
  const duration = document.getElementById('call-duration');
  const playButton = document.getElementById('call-play-audio');
  const iceServers = JSON.parse(document.getElementById('chat-ice-servers')?.textContent || '[]');
  let call = null;

  function send(current, action, data = {}) {
    return window.chatCallSend?.({conversation_id: current.conversationId, target_id: current.peerId,
      call_id: current.id, media: current.media, action, ...data}) || false;
  }
  function show(current, incoming) {
    document.getElementById('call-name').textContent = current.name;
    document.getElementById('call-avatar').textContent = Array.from(current.name)[0]?.toUpperCase() || '?';
    dialog.classList.toggle('video-call', current.media === 'video');
    dialog.classList.remove('call-connected');
    incomingControls.hidden = !incoming;
    activeControls.hidden = incoming;
    closeButton.hidden = true;
    playButton.hidden = true;
    cameraButton.hidden = current.media !== 'video';
    micButton.disabled = cameraButton.disabled = false;
    micButton.setAttribute('aria-pressed', 'false');
    cameraButton.setAttribute('aria-pressed', 'false');
    micButton.querySelector('span').textContent = 'Tắt mic';
    cameraButton.querySelector('span').textContent = 'Tắt camera';
    micButton.classList.remove('is-off');
    cameraButton.classList.remove('is-off');
    duration.hidden = true;
    local.hidden = current.media !== 'video';
    if (!dialog.open) dialog.showModal();
    status.textContent = incoming ? (current.media === 'video' ? 'Cuộc gọi video đến' : 'Cuộc gọi thoại đến') : 'Đang chuẩn bị cuộc gọi…';
  }
  function finish(text = 'Cuộc gọi đã kết thúc', notify = true) {
    const current = call;
    if (current) {
      if (notify) send(current, 'hangup');
      clearTimeout(current.timeout);
      clearTimeout(current.disconnectTimer);
      clearInterval(current.clock);
      call = null;
      current.pc?.close();
      current.stream?.getTracks().forEach(track => track.stop());
    }
    local.srcObject = null;
    local.hidden = true;
    remote.srcObject = null;
    incomingControls.hidden = activeControls.hidden = true;
    closeButton.hidden = false;
    playButton.hidden = true;
    duration.hidden = true;
    dialog.classList.remove('call-connected');
    status.textContent = text;
  }
  function fail(error) {
    const messages = {
      NotAllowedError: 'Bạn chưa cho phép dùng mic/camera. Hãy cấp quyền trong trình duyệt rồi gọi lại.',
      NotFoundError: 'Không tìm thấy mic hoặc camera phù hợp.',
      NotReadableError: 'Mic hoặc camera đang được ứng dụng khác sử dụng.',
      SecurityError: 'Trình duyệt không cho phép truy cập mic/camera trên địa chỉ này.'
    };
    finish(messages[error?.name] || error?.message || 'Không thể kết nối cuộc gọi. Vui lòng thử lại.');
  }
  function createState(data) {
    return {id: data.id, peerId: data.peerId, conversationId: data.conversationId,
      name: data.name, media: data.media, ice: [], pc: null, stream: null, offer: data.offer, answered: false};
  }
  async function prepare(current) {
    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      throw new Error('Gọi điện cần trình duyệt hỗ trợ và địa chỉ HTTPS hoặc localhost.');
    }
    const stream = await navigator.mediaDevices.getUserMedia({audio: true, video: current.media === 'video'});
    if (call !== current) { stream.getTracks().forEach(track => track.stop()); return false; }
    current.stream = stream;
    local.srcObject = stream;
    const pc = current.pc = new RTCPeerConnection({iceServers});
    stream.getTracks().forEach(track => pc.addTrack(track, stream));
    const remoteStream = new MediaStream();
    remote.srcObject = remoteStream;
    pc.ontrack = event => {
      if (call !== current) return;
      remoteStream.addTrack(event.track);
      remote.play().catch(() => { playButton.hidden = false; });
    };
    pc.onicecandidate = event => {
      if (event.candidate && call === current) send(current, 'ice', {candidate: event.candidate.toJSON()});
    };
    pc.onconnectionstatechange = () => {
      if (call !== current) return;
      if (pc.connectionState === 'connected') {
        clearTimeout(current.timeout);
        clearTimeout(current.disconnectTimer);
        status.textContent = current.media === 'video' ? 'Đang gọi video' : 'Đang gọi thoại';
        dialog.classList.add('call-connected');
        if (!current.startedAt) {
          current.startedAt = Date.now();
          duration.hidden = false;
          const tick = () => {
            const seconds = Math.floor((Date.now() - current.startedAt) / 1000);
            duration.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
          };
          tick();
          current.clock = setInterval(tick, 1000);
        }
      } else if (pc.connectionState === 'failed') {
        finish('Không thiết lập được kết nối âm thanh/video giữa hai thiết bị.');
      } else if (pc.connectionState === 'disconnected') {
        status.textContent = 'Kết nối gián đoạn, đang chờ kết nối lại…';
        current.disconnectTimer = setTimeout(() => { if (call === current) finish('Cuộc gọi bị ngắt kết nối.'); }, 12000);
      }
    };
    return true;
  }
  async function setRemote(current, description) {
    await current.pc.setRemoteDescription(description);
    for (const candidate of current.ice.splice(0)) await current.pc.addIceCandidate(candidate);
  }
  function timeout(current, text) {
    clearTimeout(current.timeout);
    current.timeout = setTimeout(() => { if (call === current) finish(text); }, 45000);
  }
  document.querySelectorAll('[data-start-call]').forEach(button => button.addEventListener('click', async () => {
    if (call) { if (!dialog.open) dialog.showModal(); return; }
    const actions = button.closest('.chat-call-actions');
    const current = call = createState({id: crypto.randomUUID(), peerId: actions.dataset.peerId,
      conversationId: actions.dataset.conversationId, name: actions.dataset.peerName, media: button.dataset.startCall});
    show(current, false);
    try {
      if (!await prepare(current)) return;
      const offer = await current.pc.createOffer();
      await current.pc.setLocalDescription(offer);
      if (call !== current) return;
      if (!send(current, 'offer', {description: {type: offer.type, sdp: offer.sdp}})) throw new Error('Kênh gọi chưa kết nối. Vui lòng thử lại sau vài giây.');
      status.textContent = 'Đang gọi… Chờ người nhận trả lời';
      timeout(current, 'Không có người trả lời. Người nhận cần mở trang Trò chuyện.');
    } catch (error) { if (call === current) fail(error); }
  }));
  document.getElementById('call-answer').addEventListener('click', async () => {
    const current = call;
    if (!current || current.answered) return;
    current.answered = true;
    incomingControls.hidden = true;
    activeControls.hidden = false;
    status.textContent = 'Đang kết nối…';
    try {
      if (!await prepare(current)) return;
      await setRemote(current, current.offer);
      const answer = await current.pc.createAnswer();
      await current.pc.setLocalDescription(answer);
      if (call !== current) return;
      if (!send(current, 'answer', {description: {type: answer.type, sdp: answer.sdp}})) throw new Error('Kênh gọi đã ngắt kết nối.');
      timeout(current, 'Không kết nối được với người gọi.');
    } catch (error) { if (call === current) fail(error); }
  });
  window.addEventListener('chat:call-signal', async event => {
    const data = event.detail;
    if (data.type === 'call.error') { if (call) finish(data.message, false); return; }
    if (data.action === 'offer') {
      if (call) {
        if (call.id !== data.call_id) send({id:data.call_id,peerId:data.sender_id,conversationId:data.conversation_id,media:data.media}, 'busy');
        return;
      }
      const current = call = createState({id: data.call_id, peerId: data.sender_id,
        conversationId: data.conversation_id, name: data.sender_name, media: data.media, offer: data.description});
      show(current, true);
      timeout(current, 'Cuộc gọi nhỡ');
      return;
    }
    const current = call;
    if (!current || current.id !== data.call_id || current.peerId !== data.sender_id || current.conversationId !== data.conversation_id) return;
    try {
      if (data.action === 'answer' && current.pc && !current.pc.remoteDescription) {
        current.answered = true;
        status.textContent = 'Đang kết nối…';
        await setRemote(current, data.description);
      } else if (data.action === 'ice') {
        if (current.pc?.remoteDescription) await current.pc.addIceCandidate(data.candidate);
        else current.ice.push(data.candidate);
      } else if (data.action === 'reject') finish('Người nhận đã từ chối cuộc gọi.', false);
      else if (data.action === 'busy') finish('Người nhận đang trong một cuộc gọi khác.', false);
      else if (data.action === 'hangup') finish('Cuộc gọi đã kết thúc.', false);
    } catch (error) { if (call === current) fail(error); }
  });
  document.getElementById('call-reject').addEventListener('click', () => { if (call) send(call, 'reject'); finish('Đã từ chối cuộc gọi', false); dialog.close(); });
  document.getElementById('call-hangup').addEventListener('click', () => { finish(); dialog.close(); });
  closeButton.addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', () => { if (call) finish(); });
  micButton.addEventListener('click', () => {
    if (!call?.stream) return;
    const tracks = call.stream.getAudioTracks();
    const enabled = !tracks[0]?.enabled;
    tracks.forEach(track => { track.enabled = enabled; });
    micButton.setAttribute('aria-pressed', String(!enabled));
    micButton.classList.toggle('is-off', !enabled);
    micButton.querySelector('span').textContent = enabled ? 'Tắt mic' : 'Bật mic';
  });
  cameraButton.addEventListener('click', () => {
    if (!call?.stream) return;
    const tracks = call.stream.getVideoTracks();
    const enabled = !tracks[0]?.enabled;
    tracks.forEach(track => { track.enabled = enabled; });
    cameraButton.setAttribute('aria-pressed', String(!enabled));
    cameraButton.classList.toggle('is-off', !enabled);
    cameraButton.querySelector('span').textContent = enabled ? 'Tắt camera' : 'Bật camera';
    local.hidden = !enabled;
  });
  playButton.addEventListener('click', () => { remote.play().then(() => { playButton.hidden = true; }).catch(() => {}); });
  window.addEventListener('pagehide', () => { if (call) finish(); });
})();
