/** How a case is scored; shown from the ⓘ next to the MER threshold. */
export function ScoringGuide() {
  return (
    <div className="scoring-guide">
      <p><strong>MER</strong> đếm lỗi theo từ, dùng để chấm: số từ sai / (số từ sai + số từ đúng), luôn trong khoảng 0–100%. <strong>CER</strong> đếm lỗi theo ký tự, chỉ để tham khảo.</p>
      <p>Đạt khi có text và MER ≤ ngưỡng. Vượt ngưỡng hoặc kết quả rỗng thì chấm Audio không đạt.</p>
      <p className="scoring-example">Ví dụ câu đọc “Bật quạt”, ngưỡng 0%:</p>
      <ul>
        <li>“bật quạt.” → Đạt (MER 0%, CER 0%)</li>
        <li>“Bật quát” → Không đạt (MER 50%, CER 12,5%: chỉ sai dấu)</li>
        <li>“Tắt quạt” → Không đạt (MER 50%, CER 25%)</li>
      </ul>
    </div>
  );
}
