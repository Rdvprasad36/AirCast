import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, RefreshControl, StatusBar } from 'react-native';

const API_BASE = 'http://localhost:8000';

const CITIES = ['Visakhapatnam', 'Vijayawada', 'Guntur', 'Tirupati', 'Nellore', 'Kurnool'];

export default function App() {
  const [city, setCity] = useState('Visakhapatnam');
  const [aqi, setAqi] = useState(null);
  const [traffic, setTraffic] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [insight, setInsight] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      const [aqiRes, trafficRes, predRes, insightRes] = await Promise.all([
        fetch(`${API_BASE}/api/live/aqi?city=${city}`).catch(() => null),
        fetch(`${API_BASE}/api/live/traffic?city=${city}`).catch(() => null),
        fetch(`${API_BASE}/api/predict/next-hour?city=${city}`).catch(() => null),
        fetch(`${API_BASE}/api/insights/root-cause?city=${city}`).catch(() => null),
      ]);
      if (aqiRes?.ok) setAqi(await aqiRes.json());
      if (trafficRes?.ok) setTraffic(await trafficRes.json());
      if (predRes?.ok) setPrediction(await predRes.json());
      if (insightRes?.ok) { const d = await insightRes.json(); setInsight(d.insight); }
    } catch (e) { console.log('Fetch error:', e); }
  };

  useEffect(() => { fetchData(); }, [city]);

  const onRefresh = async () => { setRefreshing(true); await fetchData(); setRefreshing(false); };

  const getAqiColor = (val) => {
    if (!val) return '#666';
    if (val <= 50) return '#00e400';
    if (val <= 100) return '#ffff00';
    if (val <= 150) return '#ff7e00';
    if (val <= 200) return '#ff0000';
    return '#8f3f97';
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />
      <Text style={styles.header}>{city} Dashboard</Text>
      <Text style={styles.subheader}>Andhra Pradesh, India</Text>

      {/* City Selector */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.cityRow}>
        {CITIES.map(c => (
          <Text key={c} onPress={() => setCity(c)}
            style={[styles.cityChip, city === c && styles.cityChipActive]}>{c}</Text>
        ))}
      </ScrollView>

      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#58a6ff" />}>
        {/* AQI Card */}
        <View style={[styles.card, { borderLeftColor: getAqiColor(aqi?.aqi) }]}>
          <Text style={styles.cardLabel}>Current AQI</Text>
          <Text style={[styles.cardValue, { color: getAqiColor(aqi?.aqi) }]}>{aqi?.aqi?.toFixed(0) || '—'}</Text>
          <Text style={styles.cardSub}>{aqi?.category || 'Loading...'}</Text>
        </View>

        {/* Traffic Card */}
        <View style={[styles.card, { borderLeftColor: '#ff7e00' }]}>
          <Text style={styles.cardLabel}>Traffic Congestion</Text>
          <Text style={styles.cardValue}>{traffic ? `${(traffic.congestion_index * 100).toFixed(0)}%` : '—'}</Text>
          <Text style={styles.cardSub}>{traffic?.congestion_label || 'Loading...'}</Text>
        </View>

        {/* Prediction Card */}
        <View style={[styles.card, { borderLeftColor: '#3fb950' }]}>
          <Text style={styles.cardLabel}>Predicted AQI (+1h)</Text>
          <Text style={[styles.cardValue, { color: '#3fb950' }]}>{prediction?.predicted_aqi?.toFixed(0) || '—'}</Text>
          <Text style={styles.cardSub}>Model: {prediction?.model_used || '—'}</Text>
        </View>

        {/* AI Insight */}
        <View style={[styles.card, { borderLeftColor: '#d2a8ff' }]}>
          <Text style={styles.cardLabel}>AI Insight</Text>
          <Text style={styles.insightText}>{insight || 'Analyzing data...'}</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0d1117', paddingTop: 50, paddingHorizontal: 16 },
  header: { fontSize: 24, fontWeight: '900', color: '#e6edf3', textAlign: 'center' },
  subheader: { fontSize: 12, color: '#8b949e', textAlign: 'center', marginBottom: 12 },
  cityRow: { flexDirection: 'row', marginBottom: 16, maxHeight: 40 },
  cityChip: { backgroundColor: '#161b22', color: '#8b949e', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, marginRight: 8, fontSize: 13, overflow: 'hidden' },
  cityChipActive: { backgroundColor: '#58a6ff', color: '#0d1117', fontWeight: '700' },
  card: { backgroundColor: '#161b22', borderRadius: 12, padding: 16, marginBottom: 12, borderLeftWidth: 4 },
  cardLabel: { fontSize: 12, color: '#8b949e', textTransform: 'uppercase', letterSpacing: 1, fontWeight: '600' },
  cardValue: { fontSize: 36, fontWeight: '900', color: '#e6edf3', marginVertical: 4 },
  cardSub: { fontSize: 14, color: '#8b949e', fontWeight: '600' },
  insightText: { fontSize: 14, color: '#e6edf3', marginTop: 8, lineHeight: 20 },
});
