import gspread
from google.oauth2.service_account import Credentials
from typing import Dict, List, Optional, Tuple

from ..utils.config import SERVICE_ACCOUNT_FILE, SCOPES, SPREADSHEET_ID, SHEET_NAME
from .files import norm_hobby


class SheetsManager:
    def __init__(self):
        self.creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        self.gc = gspread.authorize(self.creds)
        self.ws = self._open_or_create_sheet()

    def _open_or_create_sheet(self):
        """Открывает или создает лист в Google Sheets"""
        sh = self.gc.open_by_key(SPREADSHEET_ID)
        try:
            ws = sh.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=26)
            ws.update(["Дата"], "A1")
        return ws

    def load_headers(self) -> List[str]:
        """Загружает заголовки из первой строки"""
        headers = self.ws.row_values(1)
        if not headers:
            self.ws.update(["Дата"], "A1")
            headers = ["Дата"]
        return headers

    def ensure_columns(self, hobby_names: List[str]) -> List[str]:
        """Гарантирует наличие столбцов под каждое хобби"""
        headers = self.load_headers()
        header_norm_map = {norm_hobby(h): h for h in headers}
        to_add = []
        
        for raw in hobby_names:
            n = norm_hobby(raw)
            if n not in header_norm_map:
                to_add.append(raw.strip())
        
        if to_add:
            new_headers = headers + to_add
            self.ws.update([new_headers], f"A1:{gspread.utils.rowcol_to_a1(1, len(new_headers))}")
            return new_headers
        return headers

    def find_today_row_idx(self, target_date: str) -> Optional[int]:
        """Ищет индекс строки (1-based) по дате в колонке A"""
        dates = self.ws.col_values(1)
        for i, d in enumerate(dates, start=1):
            if d == target_date:
                return i
        return None

    def create_today_row(self, target_date: str) -> None:
        """Добавляет пустую строку с датой в A"""
        self.ws.append_row([target_date])

    def write_values(self, values: Dict[str, int], target_date: str) -> Tuple[List[str], int]:
        """
        Записывает значения в Google Sheets
        values: {hobby: stars}
        Возвращает: (финальные заголовки, индекс строки)
        """
        hobby_list = list(values.keys())
        headers = self.ensure_columns(hobby_list)
        row_idx = self.find_today_row_idx(target_date)
        
        if row_idx is None:
            self.create_today_row(target_date)
            row_idx = len(self.ws.get_all_values())

        # Карта: нормализованное название -> индекс столбца
        header_norm_to_col = {norm_hobby(h): i+1 for i, h in enumerate(headers)}

        updates = []
        for hobby, stars in values.items():
            col = header_norm_to_col[norm_hobby(hobby)]
            a1 = gspread.utils.rowcol_to_a1(row_idx, col)
            updates.append({"range": a1, "values": [[stars]]})

        if updates:
            self.ws.batch_update(updates)
        return headers, row_idx

    def get_day_data(self, target_date: str) -> Dict[str, float]:
        """Получает данные за указанный день"""
        try:
            dates = self.ws.col_values(1)
            headers = self.ws.row_values(1)
            
            for i, date_str in enumerate(dates, start=1):
                if date_str == target_date:
                    row_values = self.ws.row_values(i)
                    data = {}
                    
                    for j, header in enumerate(headers[1:], start=1):  # Пропускаем колонку даты
                        if j < len(row_values) and row_values[j]:
                            try:
                                data[header] = float(row_values[j].replace(',', '.'))
                            except ValueError:
                                data[header] = 0.0
                        else:
                            data[header] = 0.0
                    
                    return data
            return {}
        except Exception:
            return {}

    def get_total_for_date(self, target_date: str) -> float:
        """Получает общую сумму баллов за дату"""
        data = self.get_day_data(target_date)
        return sum(data.values())