from pathlib import Path
from esphome.core import CORE, ID
from esphome.coroutine import CoroPriority, coroutine_with_priority
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32, esp32_camera, meter_reader_tflite, sensor, text_sensor, binary_sensor, web_server_base, light
from esphome.const import CONF_ID
AUTO_LOAD = ['json', 'button', 'light', 'binary_sensor', 'text_sensor', 'sensor']
DEPENDENCIES = ['esp32_camera', 'meter_reader_tflite', 'web_server']
ns = cg.esphome_ns.namespace('meter_setup')
MeterSetup = ns.class_('MeterSetup', cg.Component)
TimestampCamera = ns.class_('TimestampCamera', cg.Component)
AlignedMeterReader = ns.class_('AlignedMeterReader', meter_reader_tflite.MeterReaderTFLite)
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(MeterSetup),
    cv.GenerateID("timestamp_camera_id"): cv.declare_id(TimestampCamera),
    cv.Required('camera_id'): cv.use_id(esp32_camera.ESP32Camera),
    cv.Required('reader_id'): cv.use_id(meter_reader_tflite.MeterReaderTFLite),
    cv.Required('log_id'): cv.use_id(text_sensor.TextSensor),
    cv.Required('web_server_base_id'): cv.use_id(web_server_base.WebServerBase),
    cv.Optional('illumination_id'): cv.use_id(light.AddressableLightState),
    cv.Required('value'): sensor.sensor_schema(unit_of_measurement='m³', accuracy_decimals=3, device_class='water', state_class='total_increasing'),
    cv.Optional('change', default={'name': 'Änderung zu Vorwert'}): sensor.sensor_schema(unit_of_measurement='m³', accuracy_decimals=3, state_class='measurement', icon='mdi:water-plus'),
    cv.Optional('flow', default={'name': 'Durchfluss'}): sensor.sensor_schema(unit_of_measurement='m³/h', accuracy_decimals=3, state_class='measurement', icon='mdi:water-pump'),
    cv.Optional('last_update', default={'name': 'Letzte Aktualisierung'}): text_sensor.text_sensor_schema(icon='mdi:clock-check-outline'),
    cv.Optional('status', default={'name': 'Ablesestatus'}): text_sensor.text_sensor_schema(icon='mdi:information-outline'),
    cv.Optional('error', default={'name': 'Ablesefehler'}): text_sensor.text_sensor_schema(icon='mdi:alert-circle-outline'),
    cv.Optional('reading_age', default={'name': 'Alter der letzten Ablesung'}): sensor.sensor_schema(unit_of_measurement='s', accuracy_decimals=0, entity_category='diagnostic'),
    cv.Optional('stale', default={'name': 'Ablesung veraltet'}): binary_sensor.binary_sensor_schema(device_class='problem'),
    cv.Optional('confidence', default={'name': 'Erkennungskonfidenz'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_1', default={'name': 'Konfidenz Stelle 1'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_2', default={'name': 'Konfidenz Stelle 2'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_3', default={'name': 'Konfidenz Stelle 3'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_4', default={'name': 'Konfidenz Stelle 4'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_5', default={'name': 'Konfidenz Stelle 5'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_6', default={'name': 'Konfidenz Stelle 6'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_7', default={'name': 'Konfidenz Stelle 7'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_8', default={'name': 'Konfidenz Stelle 8'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('confidence_9', default={'name': 'Konfidenz Stelle 9'}): sensor.sensor_schema(unit_of_measurement='%', accuracy_decimals=1, entity_category='diagnostic'),
    cv.Optional('problem', default={'name': 'Ableseproblem'}): binary_sensor.binary_sensor_schema(device_class='problem'),

}).extend(cv.COMPONENT_SCHEMA)
def add_dashboard_navigation():
    web = CORE.config['web_server']
    if web.get('local', False):
        raise cv.Invalid('meter_setup navigation requires web_server local: false')
    nav = Path(__file__).with_name('navigation.js').read_text(encoding='utf-8')
    path = CORE.relative_build_path('meter-navigation.js')
    existing = web.get('js_include')
    if existing and CORE.relative_config_path(existing).resolve() != path.resolve():
        nav = CORE.relative_config_path(existing).read_text(encoding='utf-8') + '\n' + nav
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(nav, encoding='utf-8')
    web['js_include'] = str(path.resolve())
    # Runs during every code generation, including validated config cache hits.

@coroutine_with_priority(CoroPriority.WEB + 1)
async def to_code(config):
    add_dashboard_navigation()
    esp32.add_idf_sdkconfig_option("CONFIG_OV5640_SUPPORT", True)
    esp32.add_idf_sdkconfig_option("CONFIG_CAMERA_AF_SUPPORT", True)
    cg.add_define("USE_LOG_LISTENERS")
    # Construct the existing reader as a subclass; keep all upstream schema/model settings.
    reader_config = CORE.config['meter_reader_tflite']
    readers = reader_config if isinstance(reader_config, list) else [reader_config]
    for entry in readers:
        if entry[CONF_ID].id == config['reader_id'].id:
            entry[CONF_ID].type = AlignedMeterReader
    if "mqtt" in CORE.config:
        for key, entity in config.items():
            if isinstance(entity, dict):
                entity.pop("mqtt_id", None)
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    for key, method in [('camera_id','set_camera'), ('reader_id','set_reader'), ('log_id','set_log'), ('web_server_base_id','set_server')]:
        cg.add(getattr(var, method)(await cg.get_variable(config[key])))
    if 'illumination_id' in config:
        cg.add(var.set_illumination(await cg.get_variable(config['illumination_id'])))
    physical_camera = await cg.get_variable(config['camera_id'])
    if 'timestamp_camera_id' not in config:
        config['timestamp_camera_id'] = ID(f"{config[CONF_ID].id}_timestamp_camera", is_declaration=True, type=TimestampCamera)
        CORE.component_ids.add(config['timestamp_camera_id'].id)
    public_camera = cg.Pvariable(config['timestamp_camera_id'], cg.RawExpression(f"meter_setup::TimestampCamera::install({physical_camera})"))
    await cg.register_component(public_camera, {})
    cg.add(physical_camera.set_idle_update_interval(0))
    cg.add(public_camera.set_power(var.get_camera_power()))
    cg.add(var.set_public_camera(public_camera))
    reader = await cg.get_variable(config['reader_id'])
    cg.add(reader.set_alignment_owner(var))
    cg.add(var.set_value(await sensor.new_sensor(config['value'])))

    for key in ['change', 'flow']:
        cg.add(getattr(var, 'set_' + key)(await sensor.new_sensor(config[key])))
    for key in ['last_update', 'status', 'error']:
        cg.add(getattr(var, 'set_' + key)(await text_sensor.new_text_sensor(config[key])))
    cg.add(var.set_problem(await binary_sensor.new_binary_sensor(config['problem'])))

    cg.add(var.set_reading_age(await sensor.new_sensor(config['reading_age'])))
    cg.add(var.set_stale(await binary_sensor.new_binary_sensor(config['stale'])))
    cg.add(var.set_confidence(await sensor.new_sensor(config['confidence'])))
    for i in range(9):
        cg.add(var.set_digit_confidence(i, await sensor.new_sensor(config[f'confidence_{i+1}'])))
