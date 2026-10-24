# แผนการดำเนินงานข้อสอบ Final IPA2026 (Implementation Plan)

เอกสารนี้จัดทำขึ้นเพื่อเป็นแนวทางและแผนการทำงานทีละขั้นตอน (Step-by-Step Guide) สำหรับการทำข้อสอบ Final **IPA2026 Student Starter** โดยเน้นชี้แนะสิ่งที่ต้องทำ ข้อกำหนดใน Spec ลำดับการพัฒนา และวิธีการทดสอบในแต่ละขั้น **โดยไม่มีการเฉลยโค้ด** เพื่อให้นักศึกษาเข้าใจระบบและลงมือเขียนโค้ดด้วยตนเองได้อย่างเป็นระบบและมั่นใจ

---

## 1. ภาพรวมของระบบและเป้าหมาย (Goal Overview)

เป้าหมายของข้อสอบคือการพัฒนา **Webex Bot สำหรับ Network Automation** ที่ทำงานดังนี้:
1. รับคำขอจาก Webex ผ่าน `@mention` บอต พร้อมแนบไฟล์คอนฟิก **YAML 1 ไฟล์**
2. รับ Event ผ่าน Webhook (`POST /webhook`) จากนั้นดาวน์โหลดข้อความและไฟล์ YAML ผ่าน Webex REST API
3. ทำการตรวจสอบความถูกต้องของ Envelope (การ mention, ไฟล์แนบ) และโครงสร้าง YAML ตามลำดับความสำคัญ (Precedence)
4. สั่งการและจัดการ Interface (`Loopback<student-id>`) บน Cisco Router ตาม `method` และ `action` ที่กำหนด
5. ส่งผลลัพธ์เป็นข้อความ JSON กลับไปยังห้อง Webex ต้นทาง
6. รองรับการทำงานใน Docker Container และผ่านการตรวจทั้ง **CI Test (10 คะแนน)** และ **Live Test (10 คะแนน)** (รวม Take-home 20 คะแนน)

```mermaid
flowchart TD
    subgraph Webex Room
        User["นักศึกษา / Grader"] -->|@mention bot + แนบ YAML| WebexAPI["Cisco Webex Cloud"]
    end

    subgraph Bot Deployment
        WebexAPI -->|Webhook Event| Tunnel["HTTPS Tunnel (เช่น Cloudflare)"]
        Tunnel -->|POST /webhook| WebhookServer["app/webhook_server.py"]
        WebhookServer -->|HTTP 200 accepted| Tunnel
        WebhookServer -->|ดึงข้อความ & โหลด YAML| WebexClient["app/webex_client.py"]
        WebhookServer --> RequestHandler["app/request_handler.py & app/core.py (Part 1)"]
        RequestHandler --> Dispatcher["app/dispatcher.py (Part 4)"]
        Dispatcher --> Planner["app/planner.py (Part 2)"]
        Dispatcher --> Backends["app/backends/ (Part 3)"]
    end

    subgraph Network Devices
        Backends -->|RESTCONF / NETCONF / Ansible / Netmiko| Router["Cisco IOS XE Router"]
    end

    WebhookServer -->|POST /messages ตอบ JSON ผลลัพธ์| WebexAPI
```

---

## 2. ข้อควรระวังและเงื่อนไขสำคัญ (User Review & Critical Warnings)

> [!CAUTION]
> **โควตาการสั่ง `grade` มีจำกัดเพียง 10 ครั้งเท่านั้น**
> การสั่งตรวจจริงในห้องสอบมีโควตา 10 ครั้ง และผลคะแนนที่ดีที่สุดจากการส่งรอบเดียวจะถูกนำมาคิดคะแนน ไม่มีการเฉลี่ยคะแนน ดังนั้น:
> - ห้ามสั่ง `grade` หากการทดสอบในเครื่องและ Student CI ยังไม่ผ่าน 100%
> - ใช้คำสั่ง `verify` ได้ฟรีไม่จำกัด เพื่อตรวจสอบความพร้อมก่อนส่งตรวจจริง

> [!WARNING]
> **ห้ามใส่ Secret หรือ Credential ใดๆ ลงใน Git Repository เด็ดขาด**
> - ห้าม commit ไฟล์ `.env`, `WEBEX_BOT_TOKEN`, `ROUTER_USER`, หรือ `ROUTER_PASS` ลง GitHub
> - Repository ต้องตั้งเป็น Public หรือหากเป็น Private ต้อง Grant Access ให้ผู้สอนตามคำแนะนำในวิชา

> [!IMPORTANT]
> **ข้อกำหนดเกี่ยวกับ IP Address และ Interface**
> - Interface ที่ใช้ทดสอบต้องเป็น `Loopback<student-id>` ของตนเองเท่านั้น (ห้ามลบหรือแก้ไขของผู้อื่น)
> - ห้ามใช้ IP ในช่วง `192.0.2.128/27` ในการทดลองด้วยมือ เพราะเป็นช่วงที่ระบบ Grader สงวนไว้ใช้ในรอบ Live Test
> - การทดสอบด้วยตนเองในห้อง `IPA2026` ให้ใช้ Router ในช่วง `10.0.29.102` – `10.0.29.105` เท่านั้น (ห้ามทดลองส่ง YAML เองบน `10.0.29.101` ซึ่งเป็น Router ห้องสอบ)

---

## 3. ตารางความเข้ากันได้ของ Method และ Action (Capability Matrix)

การเชื่อมโยงการทำงานในทุกส่วนจะต้องยึดตามตารางนี้ หากคำขอจับคู่ผิด ต้องตอบกลับด้วย `{"status":"error","result":"invalid_action"}` ทันทีโดยไม่ส่งไปยัง Router:

| Method (`method`) | `status` (อ่าน) | `plan` (วางแผน) | `apply` (ตั้งค่าจริง) | `delete` (ลบจริง) |
|---|:---:|:---:|:---:|:---:|
| `restconf` | ✓ | ✓ | ✓ | ✗ |
| `netconf` | ✓ | ✓ | ✓ | ✗ |
| `ansible` | ✗ | ✗ | ✓ | ✗ |
| `netmiko-textfsm` | ✓ | ✗ | ✗ | ✓ |

---

## 4. แผนการทำงานทีละขั้นตอน (Step-by-Step Implementation Roadmap)

### สเต็ปที่ 0: การเตรียม Environment และ Git Repository
1. **สร้าง Git Repository ของตนเอง**:
   - นำโค้ด Starter ไป Push เข้าสู่ Git Repository งานของตนเองบน GitHub
   - ทำงานบน Branch `main` เป็นหลัก
2. **สร้าง Virtual Environment สำหรับ Python**:
   - สร้าง Python 3.10+ venv: `python -m venv .venv`
   - Activate environment และติดตั้ง dependencies: `pip install -r requirements.txt`
3. **ตรวจสอบสภาพแวดล้อมการทดสอบ**:
   - ทดลองรันคำสั่ง `pytest -q tests` (จะพบว่า tests ส่วนใหญ่ยัง fail หรือ error เนื่องจากยังไม่ได้เริ่มเขียนฟังก์ชัน)

---

### สเต็ปที่ 1: Part 1 — การตรวจสอบ Envelope และเนื้อหา YAML
**ไฟล์ที่เกี่ยวข้อง**: [`app/request_handler.py`](file:///d:/Downloads/IPA2026-student-starter/app/request_handler.py), [`app/core.py`](file:///d:/Downloads/IPA2026-student-starter/app/core.py)  
**เอกสารอ้างอิงหลัก**: `specs/desired-state-spec-v1.md`, `specs/response-spec-v1.md`  
**คะแนน CI**: 2 คะแนน

#### สิ่งที่ต้องทำ:
1. **ใน `app/request_handler.py`**:
   - `validate_webex_envelope(mentioned_people, attachment_path, bot_person_id)`:
     - ตรวจสอบว่า `bot_person_id` เป็น string หรือไม่ และอยู่ในลิสต์ `mentioned_people` หรือไม่ ถ้าไม่ให้ตอบ error `missing_bot_mention`
     - ตรวจสอบว่า `attachment_path` มีค่าหรือไม่ ถ้าเป็น `None` ให้ตอบ error `no_yaml`
     - หากผ่านทั้งสองข้อ ให้ return `None`
   - `handle_webex_request(mentioned_people, attachment_path, bot_person_id)`:
     - เรียก `validate_webex_envelope` ก่อน หากมี error ให้ return ผลนั้นทันที
     - หากผ่าน ให้ส่ง `attachment_path` ไปประมวลผลต่อด้วย `process_request_file()` จาก `app/core.py`
2. **ใน `app/core.py`**:
   - `process_request_file(path)`:
     - เปิดอ่านไฟล์และ Parse ด้วย YAML parser (ต้องดักจับ `yaml.YAMLError` หรือข้อผิดพลาดในการ parse)
     - ส่งข้อมูล dictionary ที่ได้ไปให้ `validate_request(data)`
   - `validate_request(data)`:
     - ตรวจสอบตามลำดับความสำคัญ (Precedence Order) ที่เข้มงวด:
       1. Type ของ Root Data: ต้องเป็น Mapping/Dict หากไม่ใช่ ให้ตอบ `invalid_yaml`
       2. `version`: ต้องเป็น integer เลข `1` เท่านั้น (ห้าม string `"1"`, float `1.0`, หรือ boolean `true`) หากไม่ใช่ตอบ `invalid_version`
       3. `router`: ตรวจสอบว่ามีคีย์นี้ไหม (`missing_router`) และ IP ต้องอยู่ในชุด Router ที่อนุญาต `10.0.29.101`–`10.0.29.105` เท่านั้น (`invalid_router`)
       4. `method`: ตรวจสอบว่ามีคีย์นี้ไหม (`missing_method`) และต้องเป็นค่าที่รู้จัก (`invalid_method`)
       5. `action`: ตรวจสอบว่ามีคีย์นี้ไหม (`missing_action`) และต้องเข้าคู่กับ `method` ได้ตาม Capability Matrix (`invalid_action`)
       6. `desired`, `desired.interface`, `desired.interface.name`: ตรวจสอบตามลำดับ `missing_desired` -> `missing_interface` -> `missing_interface_name`
       7. ตรวจสอบฟิลด์เฉพาะตามประเภท Action:
          - กรณี `status` และ `delete`: ต้องการเพียงแค่ `name` เท่านั้น (หากมีฟิลด์อื่นแนบมาให้ละเลย ไม่นำมาตรวจสอบ)
          - กรณี `plan` และ `apply`: ต้องมี `ipv4`, `description`, `admin_state` ให้ครบ (`missing_ipv4`, `missing_description`, `missing_admin_state`) และ `admin_state` ต้องเป็น `"up"` หรือ `"down"` เท่านั้น (`invalid_admin_state`)
       8. หากทุกอย่างถูกต้อง ให้ตอบกลับ: `{"status": "ok", "result": "accepted"}`
3. **การทดสอบความถูกต้อง**:
   - รัน: `pytest tests/test_part1.py tests/test_part1_mentions.py`
   - เช็กจนกว่าทั้ง 2 ชุดทดสอบจะผ่านทั้งหมด

---

### สเต็ปที่ 2: Part 2 — ตรรกะการวางแผน (Plan Engine)
**ไฟล์ที่เกี่ยวข้อง**: [`app/planner.py`](file:///d:/Downloads/IPA2026-student-starter/app/planner.py)  
**โฟลเดอร์สำหรับเพิ่ม Test**: `sample-tests/part2/fixtures/`, `sample-tests/part2/cases/`  
**เอกสารอ้างอิงหลัก**: `specs/plan-spec-v1.md`  
**คะแนน CI**: 2 คะแนน

#### สิ่งที่ต้องทำ:
1. **ใน `app/planner.py`**:
   - ฟังก์ชัน `build_plan(desired_interface, current_interface)`:
     - รับ `desired_interface` (dictionary สมบูรณ์ที่มี name, ipv4, description, admin_state)
     - รับ `current_interface` (dictionary สถานะปัจจุบัน หรือ `None` หากยังไม่มี interface บน router)
     - **กรณี Create (`current_interface is None`)**:
       - `operation: "create"`
       - `changes`: บรรจุทั้ง 3 ฟิลด์ (`ipv4`, `description`, `admin_state`) โดยระบุเฉพาะค่า `to: <desired_value>` (หมายเหตุ: ห้ามใส่ `name` ใน `changes`)
     - **กรณี Interface มีอยู่แล้ว (`current_interface` เป็น Dict)**:
       - เปรียบเทียบค่าของ 3 ฟิลด์ที่บริหารจัดการ (`ipv4`, `description`, `admin_state`)
       - หากมีฟิลด์ที่ค่าไม่ตรงกัน:
         - `operation: "update"`
         - `changes`: ใส่เฉพาะฟิลด์ที่มีความต่างกัน ในรูปแบบ `{"from": <current_value>, "to": <desired_value>}`
       - หากค่าตรงกันทุกฟิลด์:
         - `operation: "no_change"`
         - `changes: {}` (Empty dictionary)
     - โครงสร้างผลลัพธ์: `{"status": "ok", "result": "planned", "operation": ..., "changes": ...}`
2. **สร้าง Test Cases เพิ่มเติมตามข้อกำหนดของโจทย์**:
   - ตาม Spec ข้อ 174–192 นักศึกษา**ต้องเพิ่มเคสทดสอบอย่างน้อย 3 เคส** ที่โฟลเดอร์ `sample-tests/part2/cases/` และ fixture ที่ `sample-tests/part2/fixtures/`
   - เช่น เคสที่อัปเดตเฉพาะ IP, อัปเดตเฉพาะ admin_state หรืออัปเดตหลายฟิลด์พร้อมกัน
   - **ห้ามแก้ไขไฟล์ `tests/test_part2.py`** (ระบบจะโหลดไฟล์ YAML ในโฟลเดอร์นั้นมารันอัตโนมัติ)
3. **การทดสอบความถูกต้อง**:
   - รัน: `pytest tests/test_part2.py`

---

### สเต็ปที่ 3: Part 3 — การพัฒนา Backend Adapter เชื่อมต่อ Router
**ไฟล์ที่เกี่ยวข้อง**:
- [`app/backends/planning.py`](file:///d:/Downloads/IPA2026-student-starter/app/backends/planning.py)
- [`app/backends/restconf.py`](file:///d:/Downloads/IPA2026-student-starter/app/backends/restconf.py)
- [`app/backends/netconf.py`](file:///d:/Downloads/IPA2026-student-starter/app/backends/netconf.py)
- [`app/backends/netmiko_textfsm.py`](file:///d:/Downloads/IPA2026-student-starter/app/backends/netmiko_textfsm.py)
- [`app/backends/ansible.py`](file:///d:/Downloads/IPA2026-student-starter/app/backends/ansible.py)
- [`ansible/apply_interface.yml`](file:///d:/Downloads/IPA2026-student-starter/ansible/apply_interface.yml), [`ansible/inventory.ini`](file:///d:/Downloads/IPA2026-student-starter/ansible/inventory.ini)  
**เอกสารอ้างอิงหลัก**: `specs/backend-spec-v1.md`  
**คะแนน CI**: 4 คะแนน

#### โครงสร้างและการแมป Error ที่ทุก Backend ต้องใช้ร่วมกัน:
เมื่อเกิด Error จาก Network หรือ Library ต้องแปลงเป็น 3 รูปแบบมาตรฐานเสมอ:
- `authentication_failed`: เมื่อรหัสผ่านผิด/ถูกปฏิเสธสิทธิ์ (เช่น HTTP 401/403, `PermissionError`)
- `connection_failed`: เมื่อเชื่อมต่อไม่ได้/Timeout (เช่น `requests.exceptions.Timeout`, `ncclient` connection error, `ConnectionError`)
- `backend_failed`: เมื่อส่งคำสั่งไม่สำเร็จ หรือเกิดปัญหาจาก Backend (เช่น RPC error, `RuntimeError`, TextFSM parse error)

#### ขั้นตอนการเขียนทีละส่วน:
1. **Planning Wrapper (`app/backends/planning.py`)**:
   - `plan_interface(router, desired_interface, get_interface_state)`:
     - ดึงสถานะปัจจุบันโดยเรียก `get_interface_state(router, desired_interface["name"])`
     - หากสถานะที่ได้เป็น error ให้ส่ง error นั้นกลับทันที
     - หากได้ `not_found` ให้กำหนด `current_interface = None`
     - หากได้ `found` ให้ส่ง `current_interface = response["interface"]`
     - เรียก `build_plan(desired_interface, current_interface)` จาก `app.planner` แล้วส่งผลลัพธ์กลับ
   - ทดสอบ: `pytest tests/test_part3_planning.py`

2. **RESTCONF Backend (`app/backends/restconf.py`)**:
   - `get_interface_state`:
     - Endpoint: `https://<router>/restconf/data/ietf-interfaces:interfaces/interface=<name>`
     - รับ injection parameter `http_get=None` (หากไม่มี ให้ใช้ `requests.get` พร้อม basic auth)
     - Response 404 หมายถึง `result: "not_found"`, `interface: null`
     - Response 200 ให้แปลงข้อมูล IETF interface เป็น Normalized dictionary (`name`, `ipv4` ในรูป CIDR เช่น `/32`, `description`, `admin_state`: up/down ตามฟิลด์ `enabled`)
   - `plan_interface`:
     - ใช้งาน `plan_interface` ร่วมกับ `get_interface_state`
   - `apply_interface`:
     - Endpoint: `https://<router>/restconf/data/Cisco-IOS-XE-native:native/interface/Loopback=<loopback_number>`
     - ใช้ HTTP PUT พร้อม Payload Cisco-IOS-XE-native (หาก `admin_state` เป็น `down` ต้องใส่ `"shutdown": [null]`)
     - Status 200, 201, 204 ถือว่าสำเร็จ ตอบ `{"status":"ok","result":"applied"}`
   - ทดสอบ: `pytest tests/test_part3_restconf.py`

3. **NETCONF Backend (`app/backends/netconf.py`)**:
   - `get_interface_state`:
     - ใช้ Subtree filter ของ `ietf-interfaces` เพื่อดึง `<interface>`
     - แปลง XML เป็น Normalized dictionary หากไม่มีข้อมูลให้ตอบ `not_found`
   - `plan_interface`: ส่งต่อให้ Planning wrapper
   - `apply_interface`:
     - สร้าง XML payload ภายใต้ `<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">`
     - ใช้ `<Loopback nc:operation="replace">` พร้อม `<name>`, `<description>`, `<ip>` และ `<shutdown/>` (กรณี down)
     - สั่ง `edit-config` ไปยัง `target="running"`
   - ทดสอบ: `pytest tests/test_part3_netconf.py` และ `pytest tests/test_part3_plan_wrappers.py`

4. **Netmiko + TextFSM Backend (`app/backends/netmiko_textfsm.py`)**:
   - `get_interface_state`:
     - รันคำสั่ง `show ip interface <name>` และ `show interfaces description`
     - ใช้ TextFSM template แกะข้อมูล IP, prefix, link state
     - จัดการการย่อชื่อ Loopback เช่น `Loopback123` -> `Lo123` จากคำสั่ง description
     - คืน Normalized dictionary หรือ `not_found`
   - `delete_interface`:
     - ตรวจสอบสถานะก่อน หากไม่อยู่แล้วให้ตอบ `not_found` (Idempotent)
     - หากมีอยู่ ให้ส่งคำสั่ง CLI: `no interface <name>` ผ่าน Netmiko
     - ตรวจสอบสถานะซ้ำอีกครั้ง หากหายไปแล้วให้ตอบ `{"status":"ok","result":"deleted"}`
   - ทดสอบ: `pytest tests/test_part3_netmiko_textfsm.py`

5. **Ansible Backend (`app/backends/ansible.py` และ Playbook)**:
   - ออกแบบ `ansible/apply_interface.yml` และ `ansible/inventory.ini`
   - ใน Playbook ใช้ module `cisco.ios.ios_config` พร้อมตั้งค่า `defaults: true`
   - สั่งคำสั่งคอนฟิก Interface (description, ip address, shutdown/no shutdown)
   - ใน `ansible.py`: แปลง `desired_interface` เป็นตัวแปรที่ playbook ต้องการ แล้วรันผ่าน runner function
   - ทดสอบ: `pytest tests/test_part3_ansible.py`

---

### สเต็ปที่ 4: Part 4 — การเชื่อมต่อระบบ, Webex Client และ Webhook Server
**ไฟล์ที่เกี่ยวข้อง**:
- [`app/dispatcher.py`](file:///d:/Downloads/IPA2026-student-starter/app/dispatcher.py)
- [`app/integration.py`](file:///d:/Downloads/IPA2026-student-starter/app/integration.py)
- [`app/webex_client.py`](file:///d:/Downloads/IPA2026-student-starter/app/webex_client.py)
- [`app/webhook_server.py`](file:///d:/Downloads/IPA2026-student-starter/app/webhook_server.py)  
**เอกสารอ้างอิงหลัก**: `specs/integration-spec-v1.md`, `specs/live-test-part4.md`  
**คะแนน CI**: 2 คะแนน

#### สิ่งที่ต้องทำ:
1. **Dispatcher (`app/dispatcher.py`)**:
   - `dispatch_request(data)`: รับ Request ที่ผ่านการ Validate แล้ว
   - ตรวจคู่ `(method, action)` ทั้ง 9 คู่ที่ถูกต้องตาม Capability Matrix
   - กระจายงานไปยัง Backend Module ที่ตรงกัน:
     - `status` และ `delete`: ส่ง `(router, desired["interface"]["name"])`
     - `plan` และ `apply`: ส่ง `(router, desired["interface"])`
   - ทดสอบ: `pytest tests/test_part4_dispatcher.py`

2. **Integration (`app/integration.py`)**:
   - `process_request(mentioned_people, attachment_path, bot_person_id)`:
     - ตรวจสอบ Envelope ด้วย `validate_webex_envelope`
     - อ่านและ Parse YAML จาก `attachment_path`
     - ตรวจสอบ Request ด้วย `validate_request` (จาก Part 1)
     - หากผ่าน จึงเรียก `dispatch_request(data)` แล้วส่งผลลัพธ์กลับ
   - ทดสอบ: `pytest tests/test_part4_integration.py`

3. **Webex API Client (`app/webex_client.py`)**:
   - สร้าง Class `WebexClient(token=None, session=None)`:
     - ดึง Token จาก environment variable `WEBEX_BOT_TOKEN` หากไม่ได้ส่งเข้ามา (หากไม่มีให้ raise `PermissionError`)
     - กำหนด Headers Authorization `Bearer <token>`
     - ฟังก์ชัน `get_message(message_id)`: ดึงข้อมูล JSON จาก Webex API
     - ฟังก์ชัน `download_file(file_url)`: ดาวน์โหลด Content ในรูป bytes
     - ฟังก์ชัน `send_message(room_id, text)`: โพสต์ JSON กลับไปยังห้องที่กำหนด พร้อมตั้ง Timeout 10 วินาที
   - ทดสอบ: `pytest tests/test_part4_webex_client.py`

4. **Webhook Server & Event Handler (`app/webhook_server.py`)**:
   - `WebexEventHandler`:
     - กรอง Event: รับเฉพาะ `resource == "messages"` และ `event == "created"`
     - ป้องกัน Reply Loop: ไม่ประมวลผลข้อความที่สร้างโดย Bot ตัวเอง (ทั้งจาก event metadata และตอน fetch message)
     - จัดการไฟล์แนบ:
       - ไม่มีไฟล์: ส่ง `attachment_path=None`
       - มี 1 ไฟล์: ดาวน์โหลด เขียนลงไฟล์ชั่วคราว ประมวลผล แล้วลบไฟล์ทิ้งเสมอ (แม้จะเกิด exception)
       - มากกว่า 1 ไฟล์: ตอบ error `multiple_attachments` ทันทีโดยไม่ต้องดาวน์โหลด
     - ส่ง JSON ข้อความผลลัพธ์กลับไปยัง `roomId` เดียวกันกับที่ได้รับข้อความมา
   - `make_http_handler(submit_event)`:
     - `GET /health`: คืน HTTP 200 `{"status":"ok","result":"healthy"}`
     - `POST /webhook`: ตรวจสอบความถูกต้องของ JSON แล้วส่งให้ background queue/executor คืน HTTP 200 `{"status":"ok","result":"accepted"}` ทันที (ไม่ต้องรอ Router ทำงานเสร็จ)
     - Request ที่ไม่ถูกต้อง (เช่น Body เสีย): ตอบ HTTP 400 `{"status":"error","result":"invalid_event"}`
     - Path อื่นๆ ตอบ HTTP 404
   - จัดการคิวงานของ Router ให้ทำงานเรียงตามลำดับ (Sequential) เพื่อไม่ให้คำสั่งชนกัน
   - ทดสอบ: `pytest tests/test_part4_webhook.py`

---

### สเต็ปที่ 5: การทดสอบในเครื่องและการตรวจสอบ Docker Image
**ไฟล์ที่เกี่ยวข้อง**: `Dockerfile`, `compose.yaml`, `scripts/check_webhook_image.py`

1. **รัน Unit Test ทั้งหมดในเครื่อง**:
   ```bash
   python -m pytest -q tests
   ```
   *เกณฑ์ผ่าน: ต้องผ่านครบ 88 เคส (รวมเคสที่นักศึกษาเขียนเพิ่มใน Part 2)*
2. **สร้าง Docker Image**:
   ```bash
   docker compose build webhook
   ```
3. **รัน Image Smoke Check**:
   ```bash
   python scripts/check_webhook_image.py
   ```
   *สคริปต์นี้จะจำลองการตรวจสอบ `/health` และ `/webhook` ภายใน container เสมือนกับที่ระบบผู้สอนตรวจ หากผ่านจะขึ้น `PASS: image imports and HTTP /health + /webhook`*

---

### สเต็ปที่ 6: การติดตั้ง Webex Bot, Tunnel และการทดสอบ Live ด้วยตนเอง
**ห้อง Webex**: `IPA2026`  
**Router ที่ใช้**: Router ที่ได้รับมอบหมายในช่วง `10.0.29.102` – `10.0.29.105`  
**เอกสารอ้างอิง**: `README.md` (หัวข้อตัวอย่างที่ 1–10) และ `specs/live-test-part4.md`

1. **สร้าง Webex Bot**:
   - ไปที่ Cisco Webex Developer Portal
   - สร้าง Bot โดยตั้ง **Display Name เป็นรหัสนักศึกษา 8 หลักพอดี** (เช่น `66070123`)
   - นำ Bot เข้าทั้งห้อง **`IPA2026`** และ **`IPA2026 Exam Room`**
2. **ตั้งค่า Environment ในเครื่อง**:
   - สร้างไฟล์ `.env` ในเครื่อง (อย่า commit ขึ้น git) ใส่:
     - `WEBEX_BOT_TOKEN=<token_ของบอต>`
     - `ROUTER_USER=<user_ของ_router>`
     - `ROUTER_PASS=<pass_ของ_router>`
3. **เปิด Bot และ HTTPS Tunnel**:
   - รัน Container: `docker compose up -d webhook`
   - รัน Tunnel (เช่น Cloudflare Tunnel หรือ ngrok) ไปที่พอร์ต 8000
   - ลงทะเบียน Webhook ใน Webex Developers ให้ส่ง event `messages/created` ไปที่ URL ปลายทาง เช่น `https://<tunnel-domain>/webhook`
4. **ทดสอบ Flow ในห้อง `IPA2026` ทีละข้อตาม `sample-tests/webex-manual/`**:
   1. `@mention` โดยไม่แนบไฟล์ -> คาดหวัง `{"status":"error","result":"no_yaml"}`
   2. แนบไฟล์ YAML ที่ผิดรูปแบบ -> คาดหวัง `{"status":"error","result":"invalid_yaml"}`
   3. ส่ง `status` (ตอนยังไม่มี Interface) -> คาดหวัง `not_found`
   4. ส่ง `plan` (จะสร้าง Interface) -> คาดหวัง `planned` + `operation: create`
   5. ส่ง `apply` (สร้าง Interface จริง) -> คาดหวัง `applied`
   6. ส่ง `status` ตรวจสอบ -> คาดหวัง `found` พร้อมค่าที่ตรงกับที่ apply
   7. ส่ง `plan` ซ้ำ -> คาดหวัง `planned` + `operation: no_change`
   8. ส่ง Action ที่ไม่ตรงคู่ เช่น `restconf` + `delete` -> คาดหวัง `invalid_action`
   9. ส่ง `delete` ด้วย `netmiko-textfsm` -> คาดหวัง `deleted`
   10. ส่ง `delete` ซ้ำ -> คาดหวัง `not_found`

---

### สเต็ปที่ 7: การส่งตรวจคะแนนจริงในห้องสอบ (Exam Workflow)
**ห้อง Webex**: `IPA2026 Exam Room`  
**Router ตรวจสอบ**: `10.0.29.101` (ระบบจัดการให้อัตโนมัติ)  
**บอตผู้ตรวจ**: `@IPA2026-Reference`

1. **Push โค้ดทั้งหมดขึ้น GitHub**:
   - Commit โค้ดขึ้น Branch `main`
   - เข้าไปดูที่แท็บ **Actions** ใน GitHub เพื่อดูว่า workflow `Student CI` รันผ่านสมบูรณ์ที่ SHA ล่าสุด
2. **ลงทะเบียน Repository (`register`)**:
   - ในห้อง **IPA2026 Exam Room** ใช้บัญชีนักศึกษา `@mention` บอตผู้ตรวจ:
     ```text
     @IPA2026-Reference register https://github.com/<owner>/<repo>
     ```
   - รอการตอบกลับว่าลงทะเบียนสำเร็จ (คำสั่งนี้ฟรี ไม่ใช้โควตา)
3. **ทดสอบความพร้อมด้วย `verify` (สำคัญมาก)**:
   - สั่งคำสั่ง:
     ```text
     @IPA2026-Reference verify
     ```
   - Grader จะตรวจว่า Student CI ของ SHA ล่าสุดผ่านหรือไม่ และทดลอง ping บอตของคุณในห้องสอบด้วย no-YAML และ invalid-YAML
   - หากผลเป็น "พร้อม" แสดงว่าบอตออนไลน์ ตอบในห้องสอบได้ถูกต้อง (คำสั่งนี้ฟรี ไม่ใช้โควตา)
4. **ส่งตรวจจริงด้วย `grade`**:
   - มั่นใจว่าบอตและ tunnel กำลังทำงานอยู่ จากนั้นพิมพ์:
     ```text
     @IPA2026-Reference grade
     ```
   - ระบบจะเข้าคิว รัน Full CI (Hidden tests 145 เคส) และรัน Live Test 20 เคสบน Router `10.0.29.101`
   - รอผลแจ้งคะแนน (ใช้โควตา 1 ครั้งจาก 10 ครั้ง)
5. **ดูคะแนนสรุปด้วย `score`**:
   - สามารถพิมพ์ `@IPA2026-Reference score` เพื่อดูคะแนนที่ดีที่สุดได้ตลอดเวลาโดยไม่เสียโควตา

---

## 5. แผนการตรวจสอบและเกณฑ์ประเมิน (Verification & Checklist)

| ขั้นตอน | เกณฑ์การผ่าน | ผลลัพธ์ที่ต้องการ |
|---|---|---|
| **Part 1 Tests** | `pytest tests/test_part1*.py` | ผ่านทุกเคส ไม่มี error |
| **Part 2 Tests** | `pytest tests/test_part2.py` | ผ่านทุกเคส รวมทั้ง 3+ เคสใหม่ที่เขียนเอง |
| **Part 3 Tests** | `pytest tests/test_part3*.py` | ผ่านครบทุกไฟล์ (RESTCONF, NETCONF, Ansible, Netmiko) |
| **Part 4 Tests** | `pytest tests/test_part4*.py` | ผ่านครบทุกไฟล์ (Dispatcher, Integration, Webex, Webhook) |
| **Image Check** | `python scripts/check_webhook_image.py` | แสดง `PASS: image imports and HTTP /health + /webhook` |
| **Student CI** | GitHub Actions บน `main` | เครื่องหมายถูกสีเขียวทุก Step |
| **Webex Verify** | `@IPA2026-Reference verify` | แจ้งว่า "พร้อม" |
| **Final Grade** | `@IPA2026-Reference grade` | CI 10/10 และ Live 10/10 |

---

## สรุปขั้นตอนเริ่มต้นทันที (Next Actions)
1. ติดตั้ง Virtual Environment และ Dependencies
2. เริ่มต้นเปิดไฟล์ [`app/request_handler.py`](file:///d:/Downloads/IPA2026-student-starter/app/request_handler.py) และ [`app/core.py`](file:///d:/Downloads/IPA2026-student-starter/app/core.py) เพื่อเริ่มเขียน **Part 1** เป็นอันดับแรก
3. รัน `pytest tests/test_part1.py tests/test_part1_mentions.py` เพื่อตรวจผลลัพธ์
