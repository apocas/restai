import ErroImage from '../../../assets/img/robot-404.png'
import React, {  useEffect } from "react";

function Error() {
  useEffect(() => {
    document.title = 'RestAI 404';
  }, []);
  return (
    <>
      <center><img alt="404" src={ErroImage} style={{marginTop: "50px"}}></img></center>
    </>
  );
}

export default Error;