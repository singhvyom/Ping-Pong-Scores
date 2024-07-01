import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [vstats, setStats] = useState([])
  const [hstats, setHstats] = useState([])

  useEffect(() => {
    fetchScores()
  }, []);

  const fetchScores = async () => {
    try{
      const response = await fetch('http://127.0.0.1:5000');
      const data = await response.json();
      setStats(data.Vyom);
      setHstats(data.H);
    }catch(error){
      console.log(error)
    }
    
  };

  return (
    <div className="App">
      <h1>Pingpong Scores Statistics</h1>
      <div>
          <h2>H Statistics</h2>
          <p>Win/Loss Record: {hstats.win_loss_record}</p>
          <p>Average: {hstats.average}</p>
          <p>Standard Deviation: {hstats.std_deviation}</p>
          <p>Max: {hstats.max}</p>
          <p>Min: {hstats.min}</p>

          <h2>Vyom Statistics</h2>
          <p>Win/Loss Record: {vstats.win_loss_record}</p>
          <p>Average: {vstats.average}</p>
          <p>Standard Deviation: {vstats.std_deviation}</p>
          <p>Max: {vstats.max}</p>
          <p>Min: {vstats.min}</p>
        </div>
    </div>
  )
}

export default App
