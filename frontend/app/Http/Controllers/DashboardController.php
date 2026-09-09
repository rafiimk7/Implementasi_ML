<?php

namespace App\Http\Controllers;

use App\Services\ApiService;

class DashboardController extends Controller
{
    protected $api;

    public function __construct(ApiService $api)
    {
        $this->api = $api;
    }

    public function index()
    {
        try {
            $prediction = $this->api->getPredictions();
        } catch (\Exception $e) {
            $prediction = [
                'count' => 0,
                'data'  => [],
                'error' => 'Backend API tidak dapat dijangkau. Pastikan FastAPI berjalan di port 8001.',
            ];
        }

        return view('dashboard', compact('prediction'));
    }
}