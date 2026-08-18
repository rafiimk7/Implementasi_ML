<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class ApiService
{
    protected $baseUrl = 'http://127.0.0.1:8001';

    public function getPredictions(): array
    {
        $response = Http::get($this->baseUrl . '/api/predictions');
        return $response->successful() ? $response->json() : [];
    }

    public function getPredictionByTid(string $tid): array
    {
        $response = Http::get($this->baseUrl . '/api/predictions/' . $tid);
        return $response->successful() ? $response->json() : [];
    }

}