import GaugeChart from 'react-gauge-chart'
import { Container, Row, Col, Alert } from 'react-bootstrap';
import { AuthContext } from '../../common/AuthProvider.js';
import React, { useState, useEffect, useContext } from "react";

function Hardware() {
  const [hardware, setHardware] = useState({ "cpu_load": 0, "ram_usage": 0 });
  const [error, setError] = useState([]);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const fetchHardware = () => {
    return fetch(url + "/hardware", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setHardware(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchHardware", "error": err.toString() }]);
      });
  }


  useEffect(() => {
    document.title = 'RestAI Hardware';
    fetchHardware();
    const intervalCall = setInterval(() => {
      fetchHardware();
    }, 5000);
    return () => {
      // clean up
      clearInterval(intervalCall);
    };
  }, []);
  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <h1>Hardware</h1>
        <Row>
          <Col sm={4}>
            <h5>CPU</h5>
            <GaugeChart id="gauge-chart2"
              animate={false}
              nrOfLevels={20}
              textColor='#000'
              percent={hardware && hardware.cpu_load / 100}
            />
          </Col>
          <Col sm={4}>
            <h5>RAM</h5>
            <GaugeChart id="gauge-chart2"
              animate={false}
              nrOfLevels={20}
              textColor='#000'
              percent={hardware && hardware.ram_usage / 100}
            />
          </Col>
          {Object.keys(hardware).length > 2 &&
            <Col sm={4}>
              <h5>GPU</h5>
              <GaugeChart id="gauge-chart2"
                animate={false}
                nrOfLevels={20}
                textColor='#000'
                percent={hardware && hardware.gpu_load / 100}
              />
            </Col>
          }
        </Row>
        {Object.keys(hardware).length > 2 &&
          <Row>
            <Col sm={4}>
              <h5>GPU Temp</h5>
              <GaugeChart id="gauge-chart2"
                animate={false}
                nrOfLevels={20}
                textColor='#000'
                percent={hardware && hardware.gpu_temp / 100}
                formatTextValue={value => value + 'ºC'}
              />
            </Col>
            <Col sm={4}>
              <h5>GPU Ram</h5>
              <GaugeChart id="gauge-chart2"
                animate={false}
                nrOfLevels={20}
                textColor='#000'
                percent={hardware && hardware.gpu_ram_usage / 100}
              />
            </Col>
          </Row>
        }
      </Container>


    </>
  );
}

export default Hardware;