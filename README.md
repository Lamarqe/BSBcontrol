# BSBcontrol

Components:
 - Modbus:
   - read room temperatures 
   - control heating relays
 - BSBgateway: 
   - read external temperature
   - control heating & water schedules by using
     - energy prices
     - solar production forecast
     - outside temperature (heat pump COP)
 - REST API server to allow:
   - change target room temperature (template number entity)
   - external access to all kind of values
 - REST client: communicate with Home Assistant API
   - read energy prices
   - read solar production forecast (sun duration, from weather)
   - read solar production (?)

Triggers:
 - Timeouts:
   - re-calculate heating relay status (10 seconds?)
     - re-read room temperatures
   - re-calculate heating and water schedules (6 hours?)
 - API callbacks:
   - update of target room temperature