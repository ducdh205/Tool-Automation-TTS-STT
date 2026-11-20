/** How a case is scored; shown from the ⓘ next to the WER threshold. */
export function ScoringGuide() {
  return (
    <div className="scoring-guide">
      <p><strong>WER</strong> đếm lỗi theo từ, dùng để chấm. <strong>CER</strong> đếm lỗi theo ký tự, chỉ để tham khảo.</p>
      <p>Đạt khi có text và WER ≤ ngưỡng. Vượt ngưỡng hoặc kết quả rỗng thì chấm Audio không đạt.</p>
      <p className="scoring-example">Ví dụ câu đọc “Bật quạt”, ngưỡng 0%:</p>
      <ul>
        <li>“bật quạt.” → Đạt (WER 0%, CER 0%)</li>
        <li>“Bật quát” → Không đạt (WER 50%, CER 12,5%: chỉ sai dấu)</li>
        <li>“Tắt quạt” → Không đạt (WER 50%, CER 25%)</li>
      </ul>
    </div>
  );
}
