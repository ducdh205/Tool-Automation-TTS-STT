export function DevicePanel() {
  return (
    <aside className="device">
      <div className="device-head">
        <span className="side-title">Thiết bị</span>
        <span className="muted small">Khối 2</span>
      </div>
      <div className="phone">
        <div className="phone-screen">
          <div className="phone-empty">
            <div className="phone-icon">📱</div>
            <b>Chưa kết nối thiết bị</b>
            <span className="muted small">Màn hình điện thoại (scrcpy) và chế độ ghim nút sẽ có ở Khối 2.</span>
          </div>
        </div>
      </div>
      <div className="device-log">
        <div className="side-title">Nhật ký thao tác</div>
        <div className="muted small">—</div>
      </div>
    </aside>
  );
}
