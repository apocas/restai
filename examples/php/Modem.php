<?php

class Modem {

  protected $url;
  protected $apikey;
  protected $acceptType;

  public function __construct($url = null, $apikey = null) {
    $this->url = $url;
    $this->apikey = $apikey;
    $this->acceptType = 'application/json';
  }

  public function execute($verb, $localUrl, $data = null) {
    $ch = curl_init();

    try {
      switch (strtoupper($verb)) {
        case 'GET':
        return $this->executeGet($ch, $localUrl);
        break;
        case 'POST':
        return $this->executePost($ch, $localUrl, $data);
        break;
        case 'PATCH':
        return $this->executePatch($ch, $localUrl, $data);
        break;
        case 'DELETE':
        return $this->executeDelete($ch, $localUrl);
        break;
        default:
        throw new InvalidArgumentException('Current verb (' . $verb . ') is an invalid REST verb.');
      }
    } catch (InvalidArgumentException $e) {
      curl_close($ch);
      throw $e;
    } catch (Exception $e) {
      curl_close($ch);
      throw $e;
    }
  }

  public function buildPostBody($data = null) {
    if (!is_array($data)) {
      throw new InvalidArgumentException('Invalid data input for postBody.  Array expected');
    }

    //return http_build_query($data, '', '&');
    $aux = json_encode($data);
    return $aux;
  }

  protected function executeGet($ch, $localUrl) {
    curl_setopt($ch, CURLOPT_URL, $this->url . $localUrl);
    return $this->doExecute($ch);
  }

  protected function executePost($ch, $localUrl, $data = null) {
    curl_setopt($ch, CURLOPT_URL, $this->url . $localUrl);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $this->buildPostBody($data));
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'POST');

    return $this->doExecute($ch, ['Content-Type: application/json']);
  }

  protected function executePatch($ch, $localUrl, $data) {
    curl_setopt($ch, CURLOPT_URL, $this->url . $localUrl);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $this->buildPostBody($data));
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PATCH');

    return $this->doExecute($ch, ['Content-Type: application/json']);
  }

  protected function executeDelete($ch, $localUrl) {
    curl_setopt($ch, CURLOPT_URL, $this->url . $localUrl);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'DELETE');

    return $this->doExecute($ch);
  }

  protected function doExecute(&$curlHandle, $headers = []) {
    $this->setCurlOpts($curlHandle, $headers);
    $responseBody = curl_exec($curlHandle);
    $responseInfo = curl_getinfo($curlHandle);

    curl_close($curlHandle);

    $respjson = json_decode($responseBody, true);

    return array("response" => $respjson, "info" => $responseInfo);
  }

  protected function setCurlOpts(&$curlHandle, $headers = []) {
    $headers[] = 'Accept: ' . $this->acceptType;
    if ($this->apikey !== null) {
      $headers[] = 'Authorization: Bearer ' . $this->apikey;
    }
    curl_setopt($curlHandle, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($curlHandle, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($curlHandle, CURLOPT_ENCODING, "");
    curl_setopt($curlHandle, CURLOPT_TIMEOUT, 90);
    curl_setopt($curlHandle, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($curlHandle, CURLOPT_HTTPHEADER, $headers);
  }

  public function getAcceptType() {
    return $this->acceptType;
  }

  public function setAcceptType($acceptType) {
    $this->acceptType = $acceptType;
  }

  public function getUrl() {
    return $this->url;
  }

  public function setUrl($url) {
    $this->url = $url;
  }

  public function getApikey() {
    return $this->apikey;
  }

  public function setApikey($apikey) {
    $this->apikey = $apikey;
  }

}