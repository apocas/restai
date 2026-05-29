<?php

/**
 * Minimal HTTP layer for the RESTai API.
 *
 * Auth: pass an API key (sent as `Authorization: Bearer ...`) or a
 * username + password (HTTP Basic). TLS verification is ON by default;
 * disable it only for a local server with a self-signed certificate.
 *
 * Every request returns the decoded JSON body and throws RuntimeException
 * on a non-2xx response, so callers don't have to inspect status codes.
 */
class Modem {

  protected $url;
  protected $apikey;
  protected $user;
  protected $password;
  protected $verifyTls;

  public function __construct($url, $apikey = null, $user = null, $password = null, $verifyTls = true) {
    $this->url       = rtrim($url, '/');
    $this->apikey    = $apikey;
    $this->user      = $user;
    $this->password  = $password;
    $this->verifyTls = $verifyTls;
  }

  public function get($path)            { return $this->execute('GET', $path); }
  public function post($path, $data = null)  { return $this->execute('POST', $path, $data); }
  public function patch($path, $data)   { return $this->execute('PATCH', $path, $data); }
  public function delete($path)         { return $this->execute('DELETE', $path); }

  public function execute($verb, $path, $data = null) {
    $ch = curl_init($this->url . $path);

    $headers = ['Accept: application/json'];
    if ($this->apikey !== null) {
      $headers[] = 'Authorization: Bearer ' . $this->apikey;
    } elseif ($this->user !== null) {
      curl_setopt($ch, CURLOPT_USERPWD, $this->user . ':' . $this->password);
      curl_setopt($ch, CURLOPT_HTTPAUTH, CURLAUTH_BASIC);
    }

    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, strtoupper($verb));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, $this->verifyTls ? 2 : 0);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, $this->verifyTls);
    curl_setopt($ch, CURLOPT_TIMEOUT, 300);

    if ($data !== null) {
      $headers[] = 'Content-Type: application/json';
      curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    }
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

    $body   = curl_exec($ch);
    if ($body === false) {
      $err = curl_error($ch);
      curl_close($ch);
      throw new RuntimeException("Request failed: $err");
    }
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $json = json_decode($body, true);
    if ($status < 200 || $status >= 300) {
      $detail = is_array($json) && isset($json['detail']) ? json_encode($json['detail']) : $body;
      throw new RuntimeException("HTTP $status: $detail");
    }
    return $json;
  }
}
