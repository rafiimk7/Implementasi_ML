<?php

namespace App\Http\Controllers;

use App\Services\ApiService;
use Illuminate\Http\JsonResponse;

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
            // Fallback jika backend tidak tersedia
            $prediction = [
                'count' => 0,
                'data' => [],
                'error' => 'Backend API tidak dapat dijangkau. Pastikan FastAPI berjalan di port 8001.'
            ];
        }

        return view('dashboard', compact('prediction'));
    }

    public function refresh(): JsonResponse
    {
        try {
            $result = $this->api->refreshPredictions();
            $success = ($result['status'] ?? '') === 'success';
            return response()->json($result, $success ? 200 : 500);
        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => 'Tidak dapat terhubung ke backend API. Pastikan FastAPI berjalan di port 8001.',
                'error' => $e->getMessage()
            ], 503);
        }
    }
}