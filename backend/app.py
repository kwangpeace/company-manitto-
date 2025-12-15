import json
import os
import random
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PARTICIPANTS_PATH = os.path.join(DATA_DIR, "participants.json")
MATCHES_PATH = os.path.join(DATA_DIR, "matches.json")


app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "..", "frontend"), static_url_path="")
CORS(app)


@dataclass
class Participant:
    table: int
    name: str
    email: str
    birthdate: str


@dataclass
class Match:
    table: int
    manitto_name: str
    manitto_email: str
    manitti_name: str
    manitti_email: str


def load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_name(name: str) -> str:
    return name.strip()


def normalize_birthdate(birthdate: str) -> str:
    # 기대 형식: YYMMDD 또는 YYYY-MM-DD. 여기서는 입력 그대로 비교하되 공백만 제거.
    return birthdate.strip()


def load_participants() -> List[Participant]:
    data = load_json(PARTICIPANTS_PATH, [])
    participants: List[Participant] = []
    for row in data:
        participants.append(
            Participant(
                table=int(row["table"]),
                name=str(row["name"]),
                email=normalize_email(str(row["email"])),
                birthdate=normalize_birthdate(str(row["birthdate"])),
            )
        )
    return participants


def save_participants(participants: List[Participant]) -> None:
    save_json(PARTICIPANTS_PATH, [asdict(p) for p in participants])


def save_matches(matches: List[Match]) -> None:
    save_json(MATCHES_PATH, [asdict(m) for m in matches])


def load_matches() -> List[Match]:
    data = load_json(MATCHES_PATH, [])
    matches: List[Match] = []
    for row in data:
        matches.append(
            Match(
                table=int(row["table"]),
                manitto_name=row["manitto_name"],
                manitto_email=normalize_email(row["manitto_email"]),
                manitti_name=row["manitti_name"],
                manitti_email=normalize_email(row["manitti_email"]),
            )
        )
    return matches


def group_by_table(participants: List[Participant]) -> Dict[int, List[Participant]]:
    grouped: Dict[int, List[Participant]] = {}
    for p in participants:
        grouped.setdefault(p.table, []).append(p)
    return grouped


def make_matches(participants: List[Participant], seed: int | None = None) -> List[Match]:
    if seed is not None:
        random.seed(seed)

    grouped = group_by_table(participants)
    results: List[Match] = []

    for table_no, members in grouped.items():
        if len(members) < 2:
            raise ValueError(f"테이블 {table_no} 인원이 2명 미만입니다.")

        shuffled = members.copy()
        random.shuffle(shuffled)

        if len(shuffled) == 2:
            pairs = [(shuffled[0], shuffled[1]), (shuffled[1], shuffled[0])]
        else:
            pairs = []
            for idx, manitto in enumerate(shuffled):
                manitti = shuffled[(idx + 1) % len(shuffled)]
                pairs.append((manitto, manitti))

        for manitto, manitti in pairs:
            results.append(
                Match(
                    table=table_no,
                    manitto_name=manitto.name,
                    manitto_email=manitto.email,
                    manitti_name=manitti.name,
                    manitti_email=manitti.email,
                )
            )

    return results


@app.route("/api/admin/upload", methods=["POST"])
def admin_upload():
    payload = request.get_json(force=True)
    if not isinstance(payload, list):
        return jsonify({"error": "리스트 형태의 데이터를 보내주세요."}), 400

    participants: List[Participant] = []
    try:
        for row in payload:
            participants.append(
                Participant(
                    table=int(row["table"]),
                    name=str(row["name"]).strip(),
                    email=normalize_email(str(row["email"])),
                    birthdate=normalize_birthdate(str(row["birthdate"])),
                )
            )
    except (KeyError, ValueError) as exc:
        return jsonify({"error": f"잘못된 입력 형식: {exc}"}), 400

    save_participants(participants)
    # 업로드 시 이전 매칭 결과는 리셋
    save_matches([])
    return jsonify({"message": "업로드 완료", "count": len(participants)})


@app.route("/api/admin/match", methods=["POST"])
def admin_match():
    body = request.get_json(silent=True) or {}
    seed = body.get("seed")
    try:
        seed_val = int(seed) if seed is not None else None
    except ValueError:
        return jsonify({"error": "seed는 숫자여야 합니다."}), 400

    participants = load_participants()
    if not participants:
        return jsonify({"error": "참가자 데이터가 없습니다. 먼저 업로드하세요."}), 400

    try:
        matches = make_matches(participants, seed=seed_val)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    save_matches(matches)
    return jsonify({"message": "매칭 완료", "count": len(matches)})


@app.route("/api/admin/results", methods=["GET"])
def admin_results():
    matches = load_matches()
    return jsonify([asdict(m) for m in matches])


@app.route("/api/lookup", methods=["POST"])
def lookup():
    body = request.get_json(force=True)
    name = body.get("name")
    birthdate = body.get("birthdate")
    if not name or not birthdate:
        return jsonify({"error": "name과 birthdate(생년월일)가 필요합니다."}), 400

    name_norm = normalize_name(name)
    birthdate_norm = normalize_birthdate(str(birthdate))

    participants = load_participants()
    participant = next((p for p in participants if normalize_name(p.name) == name_norm), None)
    if participant is None:
        return jsonify({"error": "참가자 명단에서 이름을 찾을 수 없습니다."}), 404
    if participant.birthdate != birthdate_norm:
        return jsonify({"error": "생년월일이 일치하지 않습니다."}), 403

    matches = load_matches()
    if not matches:
        return jsonify({"error": "아직 매칭이 진행되지 않았습니다."}), 400

    for m in matches:
        if normalize_name(m.manitto_name) == name_norm:
            message = (
                f"당신의 마니띠는 {m.manitti_name}님입니다.\n\n"
                "마니띠를 떠올리며, 정성과 센스를 담은 선물을 준비해 주세요!\n"
                "마니띠에게 본인이 마니또임을 공개해서는 안 됩니다! 비밀~ 🤫\n"
                "[선물 준비 가이드]\n"
                "금액: 15,000원 ~ 20,000원\n"
                "❌ 현금 / 기프트카드 등 무성의한 선물은 피해주세요 ❌\n"
                "작은 선물이지만, 한 해를 함께 보낸 동료에게 따뜻한 마음이 전해지는 시간이 되길 바랍니다 ✨\n"
                "받는 사람이 기분 좋게 웃을 수 있는 선물이라면 무엇이든 OK입니다!"
            )
            return jsonify(
                {
                    "your_name": m.manitto_name,
                    "table": m.table,
                    "manitti_name": m.manitti_name,
                    "manitti_email": m.manitti_email,
                    "message": message,
                }
            )

    return jsonify({"error": "해당 이름을 찾을 수 없습니다."}), 404


@app.route("/admin")
@app.route("/admin/")
def serve_admin():
    static_root = app.static_folder
    return send_from_directory(static_root, "admin.html")


@app.route("/employee")
@app.route("/employee/")
def serve_employee():
    static_root = app.static_folder
    return send_from_directory(static_root, "index.html")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    # 경로 정규화: 트레일링 슬래시 제거
    normalized = path.rstrip("/") if path else ""

    static_root = app.static_folder

    # 특정 경로 매핑
    if normalized in ("admin", "admin.html"):
        return send_from_directory(static_root, "admin.html")
    if normalized in ("employee", "employee.html"):
        return send_from_directory(static_root, "index.html")

    # 정적 파일 존재 시 그대로 전달
    target = normalized or "index.html"
    if os.path.exists(os.path.join(static_root, target)):
        return send_from_directory(static_root, target)

    # 기본: 직원용 페이지
    return send_from_directory(static_root, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)


